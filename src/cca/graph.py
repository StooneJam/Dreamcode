"""主图编排：PM 三阶段 + Collector/Insight Send fanout + Report 串行。

task_plan 之后 Collector phase 2 与 Insight 按产品 fanout 并行；
全部产品就绪后汇入 report_task。

升级路径（后续）：
- 信号路由：task_plan / report_task 后加条件边，依 has_pending_signals 走 handle_signal
- handle_signal 后路由：依被清空字段回到对应 PM 节点
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from cca.agents import collector as _collector_mod
from cca.agents import insight as _insight_mod
from cca.agents.pm import (
    handle_signal_node,
    initial_brief_node,
    report_task_node,
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
NODE_REPORT_TASK = "report_task"
NODE_REPORT = "report"
NODE_HANDLE_SIGNAL = "handle_signal"


def _collect_product_node(state: CCAState) -> dict:
    """Send fanout worker：单产品深采集。走模块引用以支持 test mock。"""
    task = CollectTask(**state["_fanout_task"])
    return _collector_mod.collect_one_product(task, state["_fanout_context"])


def _insight_product_node(state: CCAState) -> dict:
    """Send fanout worker：单产品 sentiment 分析。走模块引用以支持 test mock。"""
    task = InsightTask(**state["_fanout_task"])
    return _insight_mod.insight_one_product(task, state["_fanout_context"])


def _dispatch_collect_insight(state: CCAState) -> list[Send] | str:
    """task_plan 后 fanout 出 collect_product + insight_product 并行。

    空 tasks 时直接路由到 report_task，避免空 fanout。
    """
    raw = state.get("task_plan") or {}
    try:
        tp = TaskPlan(**raw)
    except Exception:
        return NODE_REPORT_TASK

    sends: list[Send] = []
    for ct in tp.collect_tasks:
        ctx = _collector_mod.build_collect_context(state, ct.product_name)
        sends.append(Send(NODE_COLLECT_PRODUCT, {
            "_fanout_task": ct.model_dump(),
            "_fanout_context": ctx,
        }))
    for it in tp.insight_tasks:
        ctx = _insight_mod.build_insight_context(state, it.product_name)
        sends.append(Send(NODE_INSIGHT_PRODUCT, {
            "_fanout_task": it.model_dump(),
            "_fanout_context": ctx,
        }))

    if not sends:
        return NODE_REPORT_TASK
    return sends


def build_graph(*, include_report: bool = True):
    """编译主图。

    include_report=False 时 report 节点不接入（demo 时 `--skip-report` 省 token）。
    handle_signal_node 节点保留供外部 caller 调用（不在主线边里）。
    """
    g = StateGraph(CCAState)

    g.add_node(NODE_INITIAL_BRIEF, initial_brief_node)
    g.add_node(NODE_EXPLORATION, _collector_mod.exploration_node)
    g.add_node(NODE_TASK_PLAN, task_plan_node)
    g.add_node(NODE_COLLECT_PRODUCT, _collect_product_node)
    g.add_node(NODE_INSIGHT_PRODUCT, _insight_product_node)
    g.add_node(NODE_REPORT_TASK, report_task_node)
    g.add_node(NODE_HANDLE_SIGNAL, handle_signal_node)

    g.add_edge(START, NODE_INITIAL_BRIEF)
    g.add_edge(NODE_INITIAL_BRIEF, NODE_EXPLORATION)
    g.add_edge(NODE_EXPLORATION, NODE_TASK_PLAN)

    # Send fanout：collect_product ‖ insight_product → report_task
    g.add_conditional_edges(
        NODE_TASK_PLAN, _dispatch_collect_insight,
        path_map=[NODE_COLLECT_PRODUCT, NODE_INSIGHT_PRODUCT, NODE_REPORT_TASK],
    )
    g.add_edge(NODE_COLLECT_PRODUCT, NODE_REPORT_TASK)
    g.add_edge(NODE_INSIGHT_PRODUCT, NODE_REPORT_TASK)

    if include_report:
        g.add_node(NODE_REPORT, report_node)
        g.add_edge(NODE_REPORT_TASK, NODE_REPORT)
        g.add_edge(NODE_REPORT, END)
    else:
        g.add_edge(NODE_REPORT_TASK, END)

    return g.compile()


def empty_state(user_query: str, target_product: str, user_files: list[str] | None = None) -> CCAState:
    """构造图的最小起点 state。"""
    return {
        "user_query": user_query,
        "target_product": target_product,
        "user_files": user_files,
        "initial_brief": None,
        "domain_seed": None,
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "report_task": None,
        "profiles": {},
        "review_state": [],
        "qa_results": [],
        "report_status": "pending",
        "report_md": None,
        "report_pdf_path": None,
        "qa_notes": [],
        "audit_log": [],
        "debate_results": [],
        "agent_signals": [],
        "consumed_signal_ids": [],
        "decision_log": [],
    }
