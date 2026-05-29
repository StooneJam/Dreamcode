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


def test_graph_handle_signal_routes_to_three_phase_targets() -> None:
    """handle_signal 条件边按 apply_reroute 清空字段回三个 PM 阶段或 END。"""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_HANDLE_SIGNAL, NODE_EXPLORATION) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_TASK_PLAN) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_REPORT_TASK) in edges
    assert (NODE_HANDLE_SIGNAL, "__end__") in edges


def test_graph_no_report_edge_to_end() -> None:
    """include_report=False 时 report_task 直接到 END。"""
    graph = build_graph(include_report=False)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_REPORT_TASK, "__end__") in edges


@pytest.mark.skip(reason="需要真 LLM；用 demo 脚本配 dry-run 覆盖端到端")
def test_graph_invoke_dry_run() -> None:
    """端到端 invoke 覆盖见 scripts/demo/runner.py（图模式）或 scripts/demo/dry_run.py（mock）。"""
