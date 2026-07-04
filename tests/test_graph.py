"""Main graph orchestration tests -- compilation + node topology + empty_state contract."""
from __future__ import annotations

import pytest

from cca.graph import (
    NODE_COLLECT_PRODUCT,
    NODE_EXPLORATION,
    NODE_HANDLE_SIGNAL,
    NODE_HUMAN_GATE,
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
    """The include_report=True default path has every node present (including human_gate/review)."""
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    assert NODE_INITIAL_BRIEF in nodes
    assert NODE_EXPLORATION in nodes
    assert NODE_TASK_PLAN in nodes
    assert NODE_COLLECT_PRODUCT in nodes
    assert NODE_INSIGHT_PRODUCT in nodes
    assert NODE_HUMAN_GATE in nodes
    assert NODE_REVIEW in nodes
    assert NODE_REPORT_TASK in nodes
    assert NODE_REPORT in nodes
    assert NODE_HANDLE_SIGNAL in nodes


def test_graph_compiles_with_checkpointer() -> None:
    """Compiles fine when passed a checkpointer (human_gate's interrupt/resume depends on it)."""
    from langgraph.checkpoint.memory import MemorySaver

    graph = build_graph(checkpointer=MemorySaver())
    assert NODE_HUMAN_GATE in set(graph.get_graph().nodes)


def test_graph_human_gate_to_review_edge() -> None:
    """human_gate -> review is a plain edge (no branching): the human-in-the-loop gate always precedes automatic review."""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_HUMAN_GATE, NODE_REVIEW) in edges
    # collect/insight no longer connect directly to review, must go through human_gate
    assert (NODE_COLLECT_PRODUCT, NODE_REVIEW) not in edges
    assert (NODE_INSIGHT_PRODUCT, NODE_REVIEW) not in edges


def test_graph_compiles_without_report() -> None:
    """When include_report=False, the report node is absent (the demo --skip-report path)."""
    graph = build_graph(include_report=False)
    nodes = set(graph.get_graph().nodes)
    assert NODE_REPORT not in nodes
    assert NODE_REPORT_TASK in nodes


def test_empty_state_covers_all_required_fields() -> None:
    """empty_state must cover every CCAState field, none missing, to avoid a runtime KeyError."""
    from cca.state import CCAState

    state = empty_state(user_query="x", target_product="y")
    required = set(CCAState.__annotations__.keys())
    actual = set(state.keys())
    missing = required - actual
    assert not missing, f"empty_state 漏字段: {missing}"


def test_empty_state_user_files_optional() -> None:
    """user_files defaults to None when omitted, and takes its given value when passed."""
    s1 = empty_state(user_query="x", target_product="y")
    s2 = empty_state(user_query="x", target_product="y", user_files=["a.md"])
    assert s1["user_files"] is None
    assert s2["user_files"] == ["a.md"]


def test_graph_edges_fanout_path() -> None:
    """Main path: START -> initial_brief -> exploration -> task_plan -> [fanout] ->
    human_gate -> review -> report_task -> report -> END.

    After task_plan, the conditional_edges dispatcher sends Send to
    collect_product/insight_product; workers converge into human_gate (the
    human-in-the-loop gate), then to review; review's conditional edge goes to
    handle_signal (if there's a pending signal) or report_task. handle_signal's
    conditional edge routes back to exploration/task_plan/report_task/END (based on
    which field was cleared).
    """
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    expected = [
        ("__start__", NODE_INITIAL_BRIEF),
        (NODE_INITIAL_BRIEF, NODE_EXPLORATION),
        (NODE_EXPLORATION, NODE_TASK_PLAN),
        (NODE_COLLECT_PRODUCT, NODE_HUMAN_GATE),
        (NODE_INSIGHT_PRODUCT, NODE_HUMAN_GATE),
        (NODE_HUMAN_GATE, NODE_REVIEW),
        (NODE_REPORT_TASK, NODE_REPORT),
        (NODE_REPORT, "__end__"),
    ]
    for src, dst in expected:
        assert (src, dst) in edges, f"主路径缺边 {src} → {dst}"


def test_graph_review_routes_to_handle_signal_and_report_task() -> None:
    """review's exit conditional edge must target both handle_signal and report_task."""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_REVIEW, NODE_HANDLE_SIGNAL) in edges
    assert (NODE_REVIEW, NODE_REPORT_TASK) in edges


def test_graph_handle_signal_routes_to_all_phase_targets() -> None:
    """handle_signal's conditional edge routes back to one of four PM phases or END, based on the cleared/rejected field (including initial_brief)."""
    graph = build_graph()
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_HANDLE_SIGNAL, NODE_INITIAL_BRIEF) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_EXPLORATION) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_TASK_PLAN) in edges
    assert (NODE_HANDLE_SIGNAL, NODE_REPORT_TASK) in edges
    assert (NODE_HANDLE_SIGNAL, "__end__") in edges


def test_crashing_insight_worker_does_not_clobber_collector_profile() -> None:
    """Reproduces and regression-tests a P0: on the same product key, collector
    succeeds + insight crashes; insight's _skip_result placeholder
    (dimensions=[]/sources=[]) must never blank out collector's real data after
    folding through _merge_profiles -- the reducer's single-layer guard is the only
    fallback (_skip_result does no patch-style repair itself).

    Runs the real _collect_product_node / _insight_product_node / _skip_result /
    _merge_profiles, mocking only the two worker functions (no LLM calls). Dispatch
    order is collector first, insight second, and fold happens in the same order --
    this is exactly the path where data was lost in the log-mixue incident.
    """
    from functools import reduce
    from unittest.mock import patch

    from cca.graph import _collect_product_node, _insight_product_node
    from cca.state import _merge_profiles

    fanout = {"_fanout_task": {"product_name": "瑞幸"}, "_fanout_context": {}}
    full_profile = {"profiles": {"瑞幸": {
        "product_name": "瑞幸", "dimensions": [{"name": "门店"}], "sources": ["url1"],
    }}}

    with patch("cca.graph._collector_mod.collect_one_product", return_value=full_profile), \
         patch("cca.graph._insight_mod.insight_one_product",
               side_effect=RuntimeError("doubao 429 rate limit")):
        collect_out = _collect_product_node(fanout)
        insight_out = _insight_product_node(fanout)

    # insight crashed -> _skip_result placeholder (with dimensions=[]/sources=[])
    assert insight_out["profiles"]["瑞幸"]["dimensions"] == []
    assert insight_out["review_state"][0]["status"] == "forced"

    # fold in dispatch order: the reducer's guard blocks the placeholder, collector's real data must survive
    merged = reduce(_merge_profiles, [collect_out["profiles"], insight_out["profiles"]], {})
    assert merged["瑞幸"]["dimensions"] == [{"name": "门店"}]
    assert merged["瑞幸"]["sources"] == ["url1"]


def test_route_after_review_enters_handle_signal_for_debate_only_signal() -> None:
    """A purely subjective (requires_debate=True) pending signal must also enter
    handle_signal -- it can't be dropped just because the gate only recognizes factual ones."""
    from cca.graph import NODE_HANDLE_SIGNAL as H, _route_after_review

    state = {
        "agent_signals": [{"signal_id": "s1", "requires_debate": True}],
        "consumed_signal_ids": [],
    }
    assert _route_after_review(state) == H


def test_route_after_review_skips_consumed_signal() -> None:
    """A consumed signal no longer triggers handle_signal."""
    from cca.graph import _route_after_review

    state = {
        "agent_signals": [{"signal_id": "s1", "requires_debate": True}],
        "consumed_signal_ids": ["s1"],
    }
    assert _route_after_review(state) == NODE_REPORT_TASK


def test_route_after_signal_back_to_initial_brief_when_cleared() -> None:
    """After a debate rejects initial_brief and clears the field, routing must go
    back to the initial_brief node, not fall through to END."""
    from cca.graph import _route_after_signal

    state = {
        "initial_brief": None,
        "exploration_result": {"x": 1},
        "task_plan": {"y": 1},
        "report_task": {"z": 1},
    }
    assert _route_after_signal(state) == NODE_INITIAL_BRIEF


def test_graph_no_report_edge_to_end() -> None:
    """When include_report=False, report_task goes straight to END."""
    graph = build_graph(include_report=False)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert (NODE_REPORT_TASK, "__end__") in edges


def _two_product_task_plan() -> dict:
    """A minimal task_plan: one collect_task + insight_task each for two products."""
    return {
        "target_product": "甲",
        "product_type": "SaaS",
        "competitor_names": ["甲", "乙"],
        "collect_tasks": [{"product_name": "甲"}, {"product_name": "乙"}],
        "insight_tasks": [{"product_name": "甲"}, {"product_name": "乙"}],
        "tentative_buckets": [],
    }


def test_dispatch_first_round_fanouts_all() -> None:
    """The first round has no review record -> all 4 units fan out."""
    from cca.graph import _dispatch_collect_insight

    state = empty_state(user_query="x", target_product="甲")
    state["task_plan"] = _two_product_task_plan()
    sends = _dispatch_collect_insight(state)
    assert isinstance(sends, list)
    assert len(sends) == 4


def test_dispatch_skips_passed_units_on_retry() -> None:
    """After a reroute re-plan: only re-dispatch the previous round's needs_retry units; passed/forced are skipped."""
    from cca.graph import _dispatch_collect_insight

    state = empty_state(user_query="x", target_product="甲")
    state["task_plan"] = _two_product_task_plan()
    # 甲 (A) fully passed; 乙 (B) collector needs_retry, 乙 insight forced
    state["review_state"] = [
        {"agent": "collector", "product_name": "甲", "status": "passed"},
        {"agent": "insight", "product_name": "甲", "status": "passed"},
        {"agent": "collector", "product_name": "乙", "status": "needs_retry"},
        {"agent": "insight", "product_name": "乙", "status": "forced"},
    ]
    sends = _dispatch_collect_insight(state)
    assert isinstance(sends, list)
    # only 乙 (B)'s collector needs_retry gets re-dispatched
    assert len(sends) == 1
    assert sends[0].arg["_fanout_task"]["product_name"] == "乙"


@pytest.mark.skip(reason="需要真 LLM；用 demo 脚本配 dry-run 覆盖端到端")
def test_graph_invoke_dry_run() -> None:
    """End-to-end invoke coverage lives in scripts/demo/runner.py (graph mode) or scripts/demo/dry_run.py (mock)."""
