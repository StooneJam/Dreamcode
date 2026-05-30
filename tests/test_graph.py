"""主图编排测试 —— 编译 + 节点拓扑 + empty_state 契约。"""
from __future__ import annotations

import pytest

from cca.graph import (
    NODE_COLLECT_PRODUCT,
    NODE_EXPLORATION,
    NODE_HANDLE_SIGNAL,
    NODE_INITIAL_BRIEF,
    NODE_INSIGHT_PRODUCT,
    NODE_REPORT,
    NODE_REPORT_TASK,
    NODE_REVIEW,
    NODE_TASK_PLAN,
    build_graph,
    empty_state,
)


def test_graph_compiles_with_report() -> None:
    """include_report=True 默认路径，所有 9 个节点都在（含 review）。"""
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    assert NODE_INITIAL_BRIEF in nodes
    assert NODE_EXPLORATION in nodes
    assert NODE_TASK_PLAN in nodes
    assert NODE_COLLECT_PRODUCT in nodes
    assert NODE_INSIGHT_PRODUCT in nodes
    assert NODE_REVIEW in nodes
    assert NODE_REPORT_TASK in nodes
    assert NODE_REPORT in nodes
    assert NODE_HANDLE_SIGNAL in nodes


def test_graph_compiles_without_report() -> None:
    """include_report=False 时 report 节点缺席（demo --skip-report 路径）。"""
    graph = build_graph(include_report=False)
    nodes = set(graph.get_graph().nodes)
    assert NODE_REPORT not in nodes
    assert NODE_REPORT_TASK in nodes


def test_empty_state_covers_all_required_fields() -> None:
    """empty_state 必须覆盖 CCAState 所有字段，不能漏，避免运行时 KeyError。"""
    from cca.state import CCAState

    state = empty_state(user_query="x", target_product="y")
    required = set(CCAState.__annotations__.keys())
    actual = set(state.keys())
    missing = required - actual
    assert not missing, f"empty_state 漏字段: {missing}"


def test_empty_state_user_files_optional() -> None:
    """user_files 不传时默认 None，传时按值落字段。"""
    s1 = empty_state(user_query="x", target_product="y")
    s2 = empty_state(user_query="x", target_product="y", user_files=["a.md"])
    assert s1["user_files"] is None
    assert s2["user_files"] == ["a.md"]


def test_graph_edges_fanout_path() -> None:
    """主路径：START → initial_brief → exploration → task_plan → [fanout] → review → report_task → report → END。

    task_plan 后由 conditional_edges dispatcher 派发 Send 至 collect_product / insight_product；
    worker 完成后汇入 review；review 条件边到 handle_signal（有 pending signal）或 report_task。
    handle_signal 条件边回 exploration / task_plan / report_task / END（按清空字段路由）。
    """
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    expected = [
        ("__start__", NODE_INITIAL_BRIEF),
        (NODE_INITIAL_BRIEF, NODE_EXPLORATION),
        (NODE_EXPLORATION, NODE_TASK_PLAN),
        (NODE_COLLECT_PRODUCT, NODE_REVIEW),
        (NODE_INSIGHT_PRODUCT, NODE_REVIEW),
        (NODE_REPORT_TASK, NODE_REPORT),
        (NODE_REPORT, "__end__"),
    ]
    for src, dst in expected:
        assert (src, dst) in edges, f"主路径缺边 {src} → {dst}"


def test_graph_review_routes_to_handle_signal_and_report_task() -> None:
    """review 出口的条件边目标必须含 handle_signal 和 report_task。"""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_REVIEW, NODE_HANDLE_SIGNAL) in edges
    assert (NODE_REVIEW, NODE_REPORT_TASK) in edges


def test_graph_handle_signal_routes_to_all_phase_targets() -> None:
    """handle_signal 条件边按被清空/reject 字段回四个 PM 阶段或 END（含 initial_brief）。"""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_HANDLE_SIGNAL, NODE_INITIAL_BRIEF) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_EXPLORATION) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_TASK_PLAN) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_REPORT_TASK) in edges
    assert (NODE_HANDLE_SIGNAL, "__end__") in edges


def test_route_after_review_enters_handle_signal_for_debate_only_signal() -> None:
    """纯主观（requires_debate=True）pending 也要进 handle_signal，不能因门只认 factual 被丢。"""
    from cca.graph import NODE_HANDLE_SIGNAL as H, _route_after_review

    state = {
        "agent_signals": [{"signal_id": "s1", "requires_debate": True}],
        "consumed_signal_ids": [],
    }
    assert _route_after_review(state) == H


def test_route_after_review_skips_consumed_signal() -> None:
    """已消费信号不再触发 handle_signal。"""
    from cca.graph import _route_after_review

    state = {
        "agent_signals": [{"signal_id": "s1", "requires_debate": True}],
        "consumed_signal_ids": ["s1"],
    }
    assert _route_after_review(state) == NODE_REPORT_TASK


def test_route_after_signal_back_to_initial_brief_when_cleared() -> None:
    """debate reject initial_brief 清空该字段后，路由必须回 initial_brief 节点而非落 END。"""
    from cca.graph import _route_after_signal

    state = {
        "initial_brief": None,
        "exploration_result": {"x": 1},
        "task_plan": {"y": 1},
        "report_task": {"z": 1},
    }
    assert _route_after_signal(state) == NODE_INITIAL_BRIEF


def test_graph_no_report_edge_to_end() -> None:
    """include_report=False 时 report_task 直接到 END。"""
    graph = build_graph(include_report=False)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_REPORT_TASK, "__end__") in edges


def _two_product_task_plan() -> dict:
    """最小 task_plan：两产品各一 collect_task + insight_task。"""
    return {
        "target_product": "甲",
        "product_type": "SaaS",
        "competitor_names": ["甲", "乙"],
        "collect_tasks": [{"product_name": "甲"}, {"product_name": "乙"}],
        "insight_tasks": [{"product_name": "甲"}, {"product_name": "乙"}],
        "tentative_buckets": [],
    }


def test_dispatch_first_round_fanouts_all() -> None:
    """首轮无 review 记录 → 全部 4 个 unit 都 fanout。"""
    from cca.graph import _dispatch_collect_insight

    state = empty_state(user_query="x", target_product="甲")
    state["task_plan"] = _two_product_task_plan()
    sends = _dispatch_collect_insight(state)
    assert isinstance(sends, list)
    assert len(sends) == 4


def test_dispatch_skips_passed_units_on_retry() -> None:
    """reroute 重排后：只重派上一轮 needs_retry 的 unit，passed/forced 跳过。"""
    from cca.graph import _dispatch_collect_insight

    state = empty_state(user_query="x", target_product="甲")
    state["task_plan"] = _two_product_task_plan()
    # 甲 全过；乙 collector needs_retry、乙 insight forced
    state["review_state"] = [
        {"agent": "collector", "product_name": "甲", "status": "passed"},
        {"agent": "insight", "product_name": "甲", "status": "passed"},
        {"agent": "collector", "product_name": "乙", "status": "needs_retry"},
        {"agent": "insight", "product_name": "乙", "status": "forced"},
    ]
    sends = _dispatch_collect_insight(state)
    assert isinstance(sends, list)
    # 仅 乙 collector 一个 needs_retry 被重派
    assert len(sends) == 1
    assert sends[0].arg["_fanout_task"]["product_name"] == "乙"


@pytest.mark.skip(reason="需要真 LLM；用 demo 脚本配 dry-run 覆盖端到端")
def test_graph_invoke_dry_run() -> None:
    """端到端 invoke 覆盖见 scripts/demo/runner.py（图模式）或 scripts/demo/dry_run.py（mock）。"""
