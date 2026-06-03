"""主图编排：PM 三阶段 + Collector/Insight Send fanout + Report 串行。

task_plan 之后 Collector phase 2 与 Insight 按产品 fanout 并行；
全部产品就绪后汇入 report_task。

信号路由：review 出口依 has_pending_signal 走 handle_signal，handle_signal 再依被
清空/reject 字段回对应 PM 阶段（initial_brief / exploration / task_plan / report_task）。

report 是终点：Reporter 不向 PM 发反驳信号（report → END），有意不设回路。
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
    """节点异常时产出最小 forced 占位，让流程继续。"""
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
    """Send fanout worker：单产品深采集。走模块引用以支持 test mock。"""
    task_data = state["_fanout_task"]
    product_name = task_data.get("product_name", "unknown") if isinstance(task_data, dict) else "unknown"
    try:
        task = CollectTask(**task_data)
        return _collector_mod.collect_one_product(task, state["_fanout_context"])
    except Exception as exc:
        return _skip_result("collector", product_name, exc)


def _insight_product_node(state: CCAState) -> dict:
    """Send fanout worker：单产品 sentiment 分析。走模块引用以支持 test mock。"""
    task_data = state["_fanout_task"]
    product_name = task_data.get("product_name", "unknown") if isinstance(task_data, dict) else "unknown"
    try:
        task = InsightTask(**task_data)
        return _insight_mod.insight_one_product(task, state["_fanout_context"])
    except Exception as exc:
        return _skip_result("insight", product_name, exc)


def _dispatch_collect_insight(state: CCAState) -> list[Send] | str:
    """task_plan 后 fanout 出 collect_product + insight_product 并行。

    空 tasks 时直接路由到 human_gate（再到 review），避免空 fanout。
    reroute 重跑时跳过已通过评审的产品，避免全量重采。
    """
    raw = state.get("task_plan") or {}
    try:
        tp = TaskPlan(**raw)
    except Exception:
        return NODE_HUMAN_GATE

    # 已通过评审的 (agent, product) 对不再重采
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
    """review 出口：有任何未消费 signal → handle_signal；否则 → report_task。

    判断口径与 handle_signal_node 内部一致——软（debate）/硬（reroute）信号都接，
    避免纯主观信号因门只认 factual 而被卡在外面（含上游 exploration 阶段累加的
    initial_brief 主观质疑）。reroute_count 达上限时 review_node 已把 needs_retry
    全升 forced 不再 raise signal，所以此处只需判断是否有 unconsumed pending。
    """
    raw = state.get("agent_signals") or []
    consumed = set(state.get("consumed_signal_ids") or [])
    pending = [s for s in raw if s.get("signal_id") not in consumed]
    return NODE_HANDLE_SIGNAL if pending else NODE_REPORT_TASK


def _route_after_signal(state: CCAState) -> str:
    """handle_signal 出口：按被清空（reroute）或被 reject（debate）的字段决定回到哪个 PM 阶段。

    顺序按管线先后：initial_brief → exploration → task_plan → report_task。
    accepted_with_revision 不清字段 → 落到 END（避免回路；修订已写回，下游沿用）。
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
    """编译主图。

    include_report=False 时 report 节点不接入（demo 时 `--skip-report` 省 token）。
    handle_signal_node 接在 review 出口的条件边上（见 _route_after_review）。

    checkpointer：human_gate 的 interrupt/resume 依赖它。交互式前端传 MemorySaver 等；
    非交互（脚本/测试/cache-fill）传 None——此时 human_gate 走 CCA_HUMAN_REVIEW 关闭分支直接放行。
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

    # Send fanout：collect_product ‖ insight_product → human_gate → review
    g.add_conditional_edges(
        NODE_TASK_PLAN, _dispatch_collect_insight,
        path_map=[NODE_COLLECT_PRODUCT, NODE_INSIGHT_PRODUCT, NODE_HUMAN_GATE],
    )
    g.add_edge(NODE_COLLECT_PRODUCT, NODE_HUMAN_GATE)
    g.add_edge(NODE_INSIGHT_PRODUCT, NODE_HUMAN_GATE)
    g.add_edge(NODE_HUMAN_GATE, NODE_REVIEW)

    # review 后：有 pending signal → handle_signal；否则 → report_task
    g.add_conditional_edges(
        NODE_REVIEW, _route_after_review,
        path_map=[NODE_HANDLE_SIGNAL, NODE_REPORT_TASK],
    )
    # handle_signal 后按清空/reject 字段路由回 PM 阶段
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
    """构造图的最小起点 state。"""
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
