"""
PM Agent —— 分阶段规划、下发指令、评审下游产出，处理下游信号。

不是 ReAct agent，没有工具，纯结构化规划 + 评审 + 信号分发。
入口节点：4 个阶段节点（initial_brief / task_plan / analyst_task / report_task）+
handle_signal_node。其余为内部 helper。
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
    DebateResult,
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
# 注意：analyst_task 这条辩的是 PM 下发的任务包（focus_dimensions / product_names），
# 不是 Analyst 产出的 SWOT。SWOT 终审走 call_report_reviewer skill，不在此分发表里。
_TARGET_TO_DEBATE = {
    "task_plan": "pm_taskplan",
    "analyst_task": "analyst_task",
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
    """阶段四：基于 profiles（含 SWOT）+ review_state 创建 ReportTask，同时落盘决策档案。"""
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


# 下游信号处理：debate（主观挑战）+ reroute（事实性返工）


def _read_defense(target: str, state: CCAState) -> DebatePosition:
    """从 decision_log 读取 PM 的辩护立场，零 LLM 调用。

    target 是 state 字段名（task_plan / analyst_task / report_task），与
    DecisionRecord.phase 同名。把该 phase 下所有决策的 rationale / 否决项 /
    inputs_used 聚合成一份 defense，避免依赖 task 字段的字面值。

    decision_log 内可能有同 phase 的重跑残留（add reducer 永不删），保守起见
    全量带上——LLM critique 会聚焦最相关的部分。
    """
    log: list[dict] = state.get("decision_log", []) or []
    relevant = [d for d in log if d.get("phase") == target]

    if not relevant:
        return DebatePosition(
            agent_family=PM_FAMILY,
            claim=f"PM {target} 决策（decision_log 中无对应记录）",
            evidence=["state context"],
        )

    claims: list[str] = []
    evidence: list[str] = []
    for d in relevant:
        dtype = d.get("decision_type", "other")
        rationale = d.get("rationale", "")
        claims.append(f"[{dtype}] {rationale}")
        chosen = d.get("chosen")
        if chosen:
            evidence.append(f"chosen[{dtype}]={chosen}")
        for alt in d.get("alternatives_considered", []) or []:
            opt = alt.get("option")
            reason = alt.get("rejected_reason")
            if opt and reason:
                evidence.append(f"否决 {opt}：{reason}")
        for path in d.get("inputs_used", []) or []:
            if path:
                evidence.append(f"依据 {path}")

    return DebatePosition(
        agent_family=PM_FAMILY,
        claim=" | ".join(claims),
        evidence=evidence or ["决策上下文"],
    )


# debate target → 对应的 state 任务字段
_DEBATE_TARGET_TO_TASK_FIELD = {
    "pm_taskplan": "task_plan",
    "analyst_task": "analyst_task",
    "report": "report_task",
}


def _apply_debate_result(result: DebateResult) -> dict:
    """将 debate 结果转为 state 更新。

    rejected：被否决的 task 字段置 None，触发上游路由重派该阶段。
    accepted_with_revision + revised_output：写回修订版（已通过 debate skill 的
    with_structured_output schema 校验）。
    accepted（无 revision）：仅记账，不动 task。
    """
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

    task_field = _DEBATE_TARGET_TO_TASK_FIELD.get(result.target)

    if result.final_verdict == "rejected":
        if task_field:
            updates[task_field] = None
        return updates

    if result.revised_output and task_field:
        updates[task_field] = result.revised_output
        if result.target == "pm_taskplan":
            updates["competitor_names"] = result.revised_output.get("competitor_names", [])

    return updates


def handle_signal_node(state: CCAState) -> dict:
    """处理下游 AgentSignal，独立于 4 阶段主流程。

    requires_debate=true  → debate skill（PM 从 decision_log 拼装 defense，
                            挑战方从 signal.payload 的 ChallengePayload 取 claim / evidence）
    requires_debate=false → reroute skill（事实性纠错）

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
    """主观信号 → 跨家族 debate。直接读 signal.payload 的结构化 ChallengePayload。"""
    challenge = DebatePosition(
        agent_family=CHALLENGER_FAMILY,
        claim=signal.payload.claim,
        evidence=signal.payload.evidence,
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


_REROUTE_CONTEXT_KEYS = (
    "exploration_result",
    "task_plan",
    "analyst_task",
    "report_task",
    "review_state",
    "competitor_names",
)


def _build_reroute_context(state: CCAState) -> str:
    """提取 reroute 根因分析所需的最小 state 切片。

    刻意剔除 profiles / audit_log / debate_results / decision_log 等大对象，
    避免 token 浪费——reroute 判断只看采集结果与任务派发，不需要档案明细。
    """
    slice_: dict = {k: state.get(k) for k in _REROUTE_CONTEXT_KEYS}
    return json.dumps(slice_, ensure_ascii=False, default=str)


def _handle_reroute_signal(signal: AgentSignal, state: CCAState) -> dict:
    """事实性信号 → reroute skill 根因分析 + 阶段回溯。"""
    decision = reroute(signal, _build_reroute_context(state))
    return apply_reroute(decision)
