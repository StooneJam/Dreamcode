"""主图编排：PM 三阶段 + Collector + Insight + Report 串行。

第一版纯顺序，没接信号处理回路（reroute / debate 仍走 handle_signal_node，
但由 demo 脚本或上层 caller 显式调用而非图内条件边）。

升级路径（DP-007 后续）：
- Send fanout：collect 节点改为 Send dispatcher，每产品并发
- 信号路由：task_plan / report_task 后加条件边，依 has_pending_signals 走 handle_signal
- handle_signal 后路由：依被清空字段（exploration_result / task_plan / report_task is None）回到对应 PM 节点
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from cca.agents.collector import collect_node, exploration_node
from cca.agents.insight import insight_node
from cca.agents.pm import (
    handle_signal_node,
    initial_brief_node,
    report_task_node,
    task_plan_node,
)
from cca.agents.qa_report import report_node
from cca.state import CCAState

NODE_INITIAL_BRIEF = "initial_brief"
NODE_EXPLORATION = "exploration"
NODE_TASK_PLAN = "task_plan"
NODE_COLLECT = "collect"
NODE_INSIGHT = "insight"
NODE_REPORT_TASK = "report_task"
NODE_REPORT = "report"
NODE_HANDLE_SIGNAL = "handle_signal"


def build_graph(*, include_report: bool = True):
    """编译主图。

    include_report=False 时 report 节点不接入（demo 时 `--skip-report` 省 token）。
    handle_signal_node 节点保留供外部 caller 调用（不在主线边里）。
    """
    g = StateGraph(CCAState)

    g.add_node(NODE_INITIAL_BRIEF, initial_brief_node)
    g.add_node(NODE_EXPLORATION, exploration_node)
    g.add_node(NODE_TASK_PLAN, task_plan_node)
    g.add_node(NODE_COLLECT, collect_node)
    g.add_node(NODE_INSIGHT, insight_node)
    g.add_node(NODE_REPORT_TASK, report_task_node)
    g.add_node(NODE_HANDLE_SIGNAL, handle_signal_node)

    g.add_edge(START, NODE_INITIAL_BRIEF)
    g.add_edge(NODE_INITIAL_BRIEF, NODE_EXPLORATION)
    g.add_edge(NODE_EXPLORATION, NODE_TASK_PLAN)
    g.add_edge(NODE_TASK_PLAN, NODE_COLLECT)
    g.add_edge(NODE_COLLECT, NODE_INSIGHT)
    g.add_edge(NODE_INSIGHT, NODE_REPORT_TASK)

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
