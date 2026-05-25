"""
PM Agent —— 分阶段规划、下发指令、评审下游产出，处理下游信号。

不是 ReAct agent，没有工具，纯结构化规划 + 评审 + 信号分发。
4 个阶段函数 + 1 个信号处理节点。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from langchain_core.messages import HumanMessage, SystemMessage

from cca.llm.factory import gpt
from cca.schema import (
    AgentFamily,
    AgentSignal,
    AnalystTaskOutput,
    DebatePosition,
    DecisionRecord,
    InitialBriefOutput,
    ReportTaskOutput,
    TaskPlanOutput,
)
from cca.skills.debate import DebateTarget, run_debate
from cca.skills.reroute import apply_reroute, reroute
from cca.state import CCAState

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "pm.md"

# 信号 target → debate target 映射
_TARGET_TO_DEBATE = {
    "task_plan": "pm_taskplan",
    "analyst_task": "analyst_swot",
    "report_task": "report",
}

PM_FAMILY: AgentFamily = "gpt-5"
CHALLENGER_FAMILY: AgentFamily = "deepseek"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _phase_prefix(phase: str) -> str:
    """标注当前阶段，让 LLM 在完整 prompt 中定位到对应阶段规则。"""
    return f"## 当前阶段：{phase}\n\n"


def _stamp_decisions(
    records: list[DecisionRecord],
    phase: Literal["initial_brief", "task_plan", "analyst_task", "report_task"],
) -> list[dict]:
    """覆盖 phase，把 DecisionRecord 列表落盘为 dict 列表。

    phase 字段由代码强制覆盖，防止 LLM 自报错值；ts 由 schema 的 default_factory
    在 LLM 缺省时填当前时刻，LLM 主动填写的也予以保留（审计层面可信即可）。
    """
    out: list[dict] = []
    for r in records:
        d = r.model_dump()
        d["phase"] = phase
        out.append(d)
    return out


def initial_brief_node(state: CCAState) -> dict:
    """阶段一：凭训练知识起草 InitialBrief，同时落盘决策档案。"""
    llm = gpt.with_structured_output(InitialBriefOutput)
    user = _phase_prefix("阶段一 InitialBrief") + json.dumps(
        {"user_query": state["user_query"]},
        ensure_ascii=False,
    )
    result = cast(
        InitialBriefOutput,
        llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]),
    )
    return {
        "initial_brief": result.initial_brief.model_dump(),
        "decision_log": _stamp_decisions(result.decision_records, "initial_brief"),
    }


def task_plan_node(state: CCAState) -> dict:
    """阶段二：基于 CollectorExplorationResult 创建 TaskPlan，同时落盘决策档案。"""
    llm = gpt.with_structured_output(TaskPlanOutput)
    user = _phase_prefix("阶段二 TaskPlan") + json.dumps(
        {
            "user_query": state["user_query"],
            "exploration_result": state.get("exploration_result", {}),
            "competitor_names": state.get("competitor_names", []),
        },
        ensure_ascii=False,
    )
    result = cast(
        TaskPlanOutput,
        llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]),
    )
    return {
        "task_plan": result.task_plan.model_dump(),
        "competitor_names": result.task_plan.competitor_names,
        "decision_log": _stamp_decisions(result.decision_records, "task_plan"),
    }


def analyst_task_node(state: CCAState) -> dict:
    """阶段三：基于 profiles 创建 AnalystTask，同时落盘决策档案。"""
    llm = gpt.with_structured_output(AnalystTaskOutput)
    user = _phase_prefix("阶段三 AnalystTask") + json.dumps(
        {
            "user_query": state["user_query"],
            "target_product": state["target_product"],
            "competitor_names": state.get("competitor_names", []),
            "profiles": state.get("profiles", {}),
        },
        ensure_ascii=False,
    )
    result = cast(
        AnalystTaskOutput,
        llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]),
    )
    return {
        "analyst_task": result.analyst_task.model_dump(),
        "decision_log": _stamp_decisions(result.decision_records, "analyst_task"),
    }


def report_task_node(state: CCAState) -> dict:
    """阶段四：基于 SWOT 创建 ReportTask，同时落盘决策档案。"""
    llm = gpt.with_structured_output(ReportTaskOutput)
    user = _phase_prefix("阶段四 ReportTask") + json.dumps(
        {
            "user_query": state["user_query"],
            "target_product": state["target_product"],
            "competitor_names": state.get("competitor_names", []),
            "profiles": state.get("profiles", {}),
            "review_state": state.get("review_state", []),
        },
        ensure_ascii=False,
    )
    result = cast(
        ReportTaskOutput,
        llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]),
    )
    return {
        "report_task": result.report_task.model_dump(),
        "decision_log": _stamp_decisions(result.decision_records, "report_task"),
    }


# 返工信号统一处理


def _read_defense(target: str, state: CCAState) -> DebatePosition:
    """从 state 记忆读取 PM 的辩护立场，零 LLM 调用。"""
    task = state.get(target) or {}

    if target == "task_plan":
        claim = task.get("rationale", "PM 基于 exploration_result 制定 TaskPlan")
        evidence = [
            f"product_type: {task.get('product_type', '')}",
            f"competitor_names: {task.get('competitor_names', [])}",
        ]
    elif target == "analyst_task":
        claim = f"focus_dimensions: {task.get('focus_dimensions', [])}"
        evidence = [f"product_names: {task.get('product_names', [])}"]
    elif target == "report_task":
        claim = (
            f"sections: {task.get('sections', [])}, audience: {task.get('target_audience', 'N/A')}"
        )
        evidence = [f"competitors: {task.get('competitors', [])}"]
    else:
        claim = "PM 决策"
        evidence = ["state context"]

    return DebatePosition(
        agent_family=PM_FAMILY,
        claim=claim,
        evidence=[e for e in evidence if e] or ["决策上下文"],
    )


def _apply_debate_result(result) -> dict:
    """将 debate 结果转为 state 更新。"""
    updates: dict = {
        "debate_results": [result.model_dump()],
        "audit_log": [
            {
                "agent": "pm",
                "event": "debate_applied",
                "target": result.target,
                "verdict": result.final_verdict,
            }
        ],
    }
    if result.final_verdict == "rejected":
        return updates

    if result.revised_output:
        if result.target == "pm_taskplan":
            updates["task_plan"] = result.revised_output
            updates["competitor_names"] = result.revised_output.get("competitor_names", [])
        elif result.target == "analyst_swot":
            updates["analyst_task"] = result.revised_output
        elif result.target == "report":
            updates["report_task"] = result.revised_output

    return updates


def handle_signal_node(state: CCAState) -> dict:
    """处理下游 AgentSignal，独立于 4 阶段主流程。

    requires_debate=true  → debate skill（PM 从 state 读 defense，挑战方从 signal 读 challenge_position）
    requires_debate=false → reroute skill

    同一次调用内多个信号：reroute 先处理（事实性纠错优先清理脏数据），
    debate 后处理（主观分歧基于清理后的状态再裁决）。
    list 字段（debate_results / audit_log）本地累加再返回，避免节点内 dict.update 同 key 覆盖。

    去重：state.consumed_signal_ids 记录已处理的 signal_id，本次跳过其中的信号；
    本次处理的新 signal_id 写回 consumed_signal_ids（add reducer 累加）。
    信号本体留在 agent_signals 中不删除，供回溯审计。
    """
    raw = state.get("agent_signals", [])
    if not raw:
        return {}

    consumed = set(state.get("consumed_signal_ids", []))
    signals = [AgentSignal(**s) if isinstance(s, dict) else s for s in raw]
    pending = [s for s in signals if s.signal_id not in consumed]
    if not pending:
        return {}

    ordered = [s for s in pending if not s.requires_debate] + [
        s for s in pending if s.requires_debate
    ]

    debate_results: list[dict] = []
    audit_log: list[dict] = []
    scalar_updates: dict = {}

    for signal in ordered:
        partial = (
            _handle_debate_signal(signal, state)
            if signal.requires_debate
            else _handle_reroute_signal(signal, state)
        )
        debate_results.extend(partial.pop("debate_results", []))
        audit_log.extend(partial.pop("audit_log", []))
        scalar_updates.update(partial)

    return {
        **scalar_updates,
        "debate_results": debate_results,
        "audit_log": audit_log,
        "consumed_signal_ids": [s.signal_id for s in ordered],
    }


def _handle_debate_signal(signal: AgentSignal, state: CCAState) -> dict:
    """主观信号 → 跨家族 debate。"""
    challenge = DebatePosition(
        agent_family=CHALLENGER_FAMILY,
        claim=signal.payload.get("reason", ""),
        evidence=[signal.payload.get("reason", "")],
    )
    defense = _read_defense(signal.target, state)
    debate_target = cast(DebateTarget, _TARGET_TO_DEBATE.get(signal.target, "pm_taskplan"))
    target_content = state.get(signal.target) or {}

    result = run_debate(
        target=debate_target,
        target_content=target_content if isinstance(target_content, dict) else {},
        seed_positions={PM_FAMILY: defense, CHALLENGER_FAMILY: challenge},
    )
    return _apply_debate_result(result)


def _handle_reroute_signal(signal: AgentSignal, state: CCAState) -> dict:
    """事实性信号 → reroute skill 根因分析 + 阶段回溯。"""
    state_json = json.dumps(
        {k: v for k, v in state.items() if k != "agent_signals"},
        ensure_ascii=False,
        default=str,
    )
    decision = reroute(signal, state_json)
    return apply_reroute(decision, dict(state))
