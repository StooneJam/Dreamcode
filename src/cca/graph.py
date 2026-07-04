"""Main graph orchestration: PM's three phases + Collector/Insight Send fanout + Report in series.

After task_plan, Collector phase 2 and Insight fan out in parallel per product;
once all products are ready they converge into report_task.

Signal routing: review's exit routes to handle_signal based on has_pending_signal;
handle_signal then routes back to the corresponding PM phase (initial_brief /
exploration / task_plan / report_task) based on which field got cleared/rejected.

report is a terminal node: Reporter never sends a rebuttal signal back to PM
(report -> END) -- no loop back by design.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from cca.agents import collector as _collector_mod
from cca.agents import insight as _insight_mod
from cca.agents.pm import (
    handle_signal_node,
    human_gate_node,
    initial_brief_node,
    report_task_node,
    review_node,
    task_plan_node,
)
from cca.agents.qa_report import report_node
from cca.schema import CollectTask, InsightTask, TaskPlan
from cca.state import CCAState

NODE_INITIAL_BRIEF = "initial_brief"
NODE_EXPLORATION = "exploration"
NODE_TASK_PLAN = "task_plan"
NODE_COLLECT_PRODUCT = "collect_product"
NODE_INSIGHT_PRODUCT = "insight_product"
NODE_HUMAN_GATE = "human_gate"
NODE_REVIEW = "review"
NODE_REPORT_TASK = "report_task"
NODE_REPORT = "report"
NODE_HANDLE_SIGNAL = "handle_signal"


def _skip_result(agent: str, product_name: str, exc: Exception) -> dict:
    """Produce a minimal forced placeholder on node exception so the pipeline can continue."""
    from datetime import datetime, timezone
    note = f"{type(exc).__name__}: {str(exc)[:200]}"
    return {
        "profiles": {product_name: {"product_name": product_name, "company": None,
                                     "dimensions": [], "sources": []}},
        "review_state": [{"agent": agent, "product_name": product_name,
                          "status": "forced", "retry_count": 0,
                          "qa_flags": [f"节点异常已跳过：{note}"],
                          "pm_note": "节点崩溃，强制放行", "reviewed_at": None}],
        "audit_log": [{"agent": agent, "event": "node_skipped",
                       "product": product_name, "error": note,
                       "ts": datetime.now(timezone.utc).isoformat()}],
    }


def _collect_product_node(state: CCAState) -> dict:
    """Send fanout worker: deep collection for a single product. Calls via module
    reference so tests can mock it."""
    task_data = state["_fanout_task"]
    product_name = task_data.get("product_name", "unknown") if isinstance(task_data, dict) else "unknown"
    try:
        task = CollectTask(**task_data)
        return _collector_mod.collect_one_product(task, state["_fanout_context"])
    except Exception as exc:
        return _skip_result("collector", product_name, exc)


def _insight_product_node(state: CCAState) -> dict:
    """Send fanout worker: sentiment analysis for a single product. Calls via module
    reference so tests can mock it."""
    task_data = state["_fanout_task"]
    product_name = task_data.get("product_name", "unknown") if isinstance(task_data, dict) else "unknown"
    try:
        task = InsightTask(**task_data)
        return _insight_mod.insight_one_product(task, state["_fanout_context"])
    except Exception as exc:
        return _skip_result("insight", product_name, exc)


def _dispatch_collect_insight(state: CCAState) -> list[Send] | str:
    """After task_plan, fan out collect_product + insight_product in parallel.

    Empty tasks route straight to human_gate (then review), avoiding an empty fanout.
    On a reroute re-run, products that already passed review are skipped to avoid
    re-collecting everything.
    """
    raw = state.get("task_plan") or {}
    try:
        tp = TaskPlan(**raw)
    except Exception:
        return NODE_HUMAN_GATE

    # (agent, product) pairs that already passed review are not re-collected
    passed = {
        (rs["agent"], rs["product_name"])
        for rs in (state.get("review_state") or [])
        if rs.get("status") in ("passed", "forced")
    }

    sends: list[Send] = []
    for ct in tp.collect_tasks:
        if ("collector", ct.product_name) in passed:
            continue
        ctx = _collector_mod.build_collect_context(state, ct.product_name)
        sends.append(Send(NODE_COLLECT_PRODUCT, {
            "_fanout_task": ct.model_dump(),
            "_fanout_context": ctx,
        }))
    for it in tp.insight_tasks:
        if ("insight", it.product_name) in passed:
            continue
        ctx = _insight_mod.build_insight_context(state, it.product_name)
        sends.append(Send(NODE_INSIGHT_PRODUCT, {
            "_fanout_task": it.model_dump(),
            "_fanout_context": ctx,
        }))

    if not sends:
        return NODE_HUMAN_GATE
    return sends


def _route_after_review(state: CCAState) -> str:
    """review's exit: any unconsumed signal -> handle_signal; otherwise -> report_task.

    Matches handle_signal_node's own criteria -- both soft (debate) and hard (reroute)
    signals are accepted, so a purely subjective signal isn't blocked by a
    factual-only gate (this includes subjective challenges accumulated from the
    upstream exploration/initial_brief phase). Once reroute_count hits the limit,
    review_node has already escalated all needs_retry to forced and stops raising
    signals, so this only needs to check for unconsumed pending signals.
    """
    raw = state.get("agent_signals") or []
    consumed = set(state.get("consumed_signal_ids") or [])
    pending = [s for s in raw if s.get("signal_id") not in consumed]
    return NODE_HANDLE_SIGNAL if pending else NODE_REPORT_TASK


def _route_after_signal(state: CCAState) -> str:
    """handle_signal's exit: routes back to whichever PM phase had its field
    cleared (reroute) or rejected (debate).

    Ordered by pipeline sequence: initial_brief -> exploration -> task_plan -> report_task.
    accepted_with_revision clears no field -> falls through to END (no loop back;
    the revision is already written back and downstream reuses it).
    """
    if state.get("initial_brief") is None:
        return NODE_INITIAL_BRIEF
    if state.get("exploration_result") is None:
        return NODE_EXPLORATION
    if state.get("task_plan") is None:
        return NODE_TASK_PLAN
    if state.get("report_task") is None:
        return NODE_REPORT_TASK
    return END


def build_graph(*, include_report: bool = True, checkpointer=None):
    """Compile the main graph.

    include_report=False skips wiring in the report node (saves tokens for demo's `--skip-report`).
    handle_signal_node sits on review's conditional exit edge (see _route_after_review).

    checkpointer: human_gate's interrupt/resume depends on it. The interactive frontend
    passes a MemorySaver etc.; non-interactive callers (scripts/tests/cache-fill) pass
    None -- in that case human_gate's CCA_HUMAN_REVIEW-off branch passes straight through.
    """
    g = StateGraph(CCAState)

    g.add_node(NODE_INITIAL_BRIEF, initial_brief_node)
    g.add_node(NODE_EXPLORATION, _collector_mod.exploration_node)
    g.add_node(NODE_TASK_PLAN, task_plan_node)
    g.add_node(NODE_COLLECT_PRODUCT, _collect_product_node)
    g.add_node(NODE_INSIGHT_PRODUCT, _insight_product_node)
    g.add_node(NODE_HUMAN_GATE, human_gate_node)
    g.add_node(NODE_REVIEW, review_node)
    g.add_node(NODE_REPORT_TASK, report_task_node)
    g.add_node(NODE_HANDLE_SIGNAL, handle_signal_node)

    g.add_edge(START, NODE_INITIAL_BRIEF)
    g.add_edge(NODE_INITIAL_BRIEF, NODE_EXPLORATION)
    g.add_edge(NODE_EXPLORATION, NODE_TASK_PLAN)

    # Send fanout: collect_product || insight_product -> human_gate -> review
    g.add_conditional_edges(
        NODE_TASK_PLAN, _dispatch_collect_insight,
        path_map=[NODE_COLLECT_PRODUCT, NODE_INSIGHT_PRODUCT, NODE_HUMAN_GATE],
    )
    g.add_edge(NODE_COLLECT_PRODUCT, NODE_HUMAN_GATE)
    g.add_edge(NODE_INSIGHT_PRODUCT, NODE_HUMAN_GATE)
    g.add_edge(NODE_HUMAN_GATE, NODE_REVIEW)

    # after review: pending signal -> handle_signal; otherwise -> report_task
    g.add_conditional_edges(
        NODE_REVIEW, _route_after_review,
        path_map=[NODE_HANDLE_SIGNAL, NODE_REPORT_TASK],
    )
    # after handle_signal: route back to a PM phase based on the cleared/rejected field
    g.add_conditional_edges(
        NODE_HANDLE_SIGNAL, _route_after_signal,
        path_map=[NODE_INITIAL_BRIEF, NODE_EXPLORATION, NODE_TASK_PLAN, NODE_REPORT_TASK, END],
    )

    if include_report:
        g.add_node(NODE_REPORT, report_node)
        g.add_edge(NODE_REPORT_TASK, NODE_REPORT)
        g.add_edge(NODE_REPORT, END)
    else:
        g.add_edge(NODE_REPORT_TASK, END)

    return g.compile(checkpointer=checkpointer)


def empty_state(user_query: str, target_product: str, user_files: list[str] | None = None) -> CCAState:
    """Build the graph's minimal starting state."""
    from datetime import datetime, timezone
    return {
        "user_query": user_query,
        "target_product": target_product,
        "report_language": "zh",
        "user_files": user_files,
        "initial_brief": None,
        "domain_seed": None,
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "report_task": None,
        "profiles": {},
        "review_state": [],
        "reroute_count": 0,
        "human_review_feedback": None,
        "human_review_done": False,
        "human_feedback_consumed": False,
        "qa_results": [],
        "report_status": "pending",
        "report_md": None,
        "report_pdf_path": None,
        "analysis_start_ts": datetime.now(timezone.utc).isoformat(),
        "analysis_end_ts": None,
        "qa_notes": [],
        "audit_log": [],
        "debate_results": [],
        "agent_signals": [],
        "consumed_signal_ids": [],
        "decision_log": [],
    }
