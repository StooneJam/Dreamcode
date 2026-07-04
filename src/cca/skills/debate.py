"""Cross-family debate skill.

Used at:
    pm_taskplan -- a downstream subjective challenge to TaskPlan
    report     -- Reporter's challenge to ReportTask / call_report_reviewer's final review

Flow: the caller injects seed_positions -> Critique -> Refine -> converges as soon as
either side concedes, otherwise the Judge arbitrates. The judge must differ from both debaters.
"""
from __future__ import annotations

import json
from typing import Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import DEV_DOUBAO_OVERRIDE, get_llm


def _struct_method() -> str:
    """LLM structured-output method dispatches on the dev override flag:
    - Doubao override: function_calling (Doubao doesn't support response_format=json_object)
    - normal three-family path: json_mode (D-029 #3, natural field naming + better parse tolerance)
    Switching back to three families just needs unset CCA_DEV_MODEL_OVERRIDE, zero business-code changes.
    """
    return "function_calling" if DEV_DOUBAO_OVERRIDE else "json_mode"
from cca.schema import (
    AgentFamily,
    DebatePosition,
    DebateResult,
    DebateRound,
    InitialBrief,
    ReportTask,
    TaskPlan,
)

DebateTarget = Literal["pm_taskplan", "report", "pm_initial_brief"]

# schema validation table for producing revised_output at convergence
_REVISED_OUTPUT_SCHEMA: dict[DebateTarget, type[BaseModel]] = {
    "pm_taskplan": TaskPlan,
    "report": ReportTask,
    "pm_initial_brief": InitialBrief,
}

_VALID_PLATFORMS: frozenset[str] = frozenset({"appstore_cn", "appstore_us", "zhihu", "weibo", "other"})


def _repair_for_schema(data: dict, target: DebateTarget) -> dict:
    """Fix common schema deviations the LLM produces in revised_output.

    Known deviations, pm_taskplan only:
    - competitor_groups used instead of competitor_names
    - target_platforms written as free-text instead of the enum
    """
    if target != "pm_taskplan":
        return data
    data = dict(data)
    if "competitor_names" not in data and "competitor_groups" in data:
        data["competitor_names"] = [
            g["product_name"] for g in data["competitor_groups"]
            if isinstance(g, dict) and "product_name" in g
        ]
    for task in data.get("insight_tasks") or []:
        if isinstance(task, dict) and "target_platforms" in task:
            task["target_platforms"] = [
                p if p in _VALID_PLATFORMS else "other"
                for p in task["target_platforms"]
            ]
    return data


# critique / refinement use json_mode's natural field naming to avoid parse failures
class _Critique(BaseModel):
    critique: str = Field(description="A specific rebuttal of the other side's position, pointing out at least 1 problem")


class _Refinement(BaseModel):
    refinement: str = Field(description="The revised position after the other side's critique")
    still_disagrees: bool = Field(description="Whether there's still disagreement after this round's revision")


# ── three-phase implementation ──────────────────────────────────────────


def _phase_critique(family: AgentFamily, mine: DebatePosition, other: DebatePosition) -> str:
    llm = get_llm(family).with_structured_output(_Critique, method=_struct_method())
    sys = (
        f"你是 {family} 家族。请针对 {other.agent_family} 的观点写出批驳。"
        "聚焦事实：哪些 claim 不成立、哪些 evidence 太弱。每条批驳指向对方原文具体段落。"
        '以 JSON 输出：{"critique": "..."}。critique 必须是单一字符串。'
    )
    user = json.dumps(
        {"my_position": mine.model_dump(), "other_position": other.model_dump()},
        ensure_ascii=False,
    )
    return cast(_Critique, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)])).critique


def _phase_refine(family: AgentFamily, mine: DebatePosition, critique: str) -> _Refinement:
    llm = get_llm(family).with_structured_output(_Refinement, method=_struct_method())
    sys = (
        f"你是 {family} 家族。基于对方批驳修订观点，三选一：(a) 维持原 claim + 加强 evidence "
        "(b) 部分修订 (c) 撤回接受批驳。说明选择和理由。"
        'JSON 输出：{"refinement": "...", "still_disagrees": true/false}。'
        "still_disagrees=false 表示接受批驳。"
    )
    user = json.dumps(
        {"my_position": mine.model_dump(), "critique_from_other": critique},
        ensure_ascii=False,
    )
    return cast(_Refinement, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]))


def _phase_judge(
    judge: AgentFamily, target: DebateTarget, target_content: dict, rounds: list[DebateRound],
) -> DebateResult:
    """When debate doesn't converge naturally, a third family arbitrates. judge / target / rounds are force-overwritten by code."""
    llm = get_llm(judge).with_structured_output(DebateResult, method=_struct_method())
    sys = (
        f"你是 {judge} 家族的独立仲裁者。两辩方对 {target} 完成 {len(rounds)} 轮辩论。"
        "综合最后一轮 refinements 给出 final_verdict："
        "accepted / rejected / accepted_with_revision（给出 revised_output）。"
        "只看事实是否站得住，不偏袒任一方。JSON 输出符合 DebateResult schema。"
    )
    user = json.dumps(
        {"target": target, "target_content": target_content,
         "rounds": [r.model_dump() for r in rounds]},
        ensure_ascii=False,
    )
    result = cast(DebateResult, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]))
    result.judge_family = judge
    result.target = target
    result.rounds = rounds
    return result


def _phase_finalize_converged(
    winner_family: AgentFamily, target: DebateTarget,
    target_content: dict, winning_refinement: str,
) -> dict:
    """The winning side structures the consensus into a revised target_content.

    Two paths chosen by dev override (the old path isn't deleted, so switching back
    to three families reuses it directly):
    - Doubao override: with_structured_output(function_calling) -- Doubao doesn't support json_object
    - normal three-family path: bind(response_format=json_object) + manual parse + _repair_for_schema
    """
    if DEV_DOUBAO_OVERRIDE:
        return _finalize_via_function_calling(winner_family, target, target_content, winning_refinement)
    return _finalize_via_json_object(winner_family, target, target_content, winning_refinement)


def _finalize_via_function_calling(
    winner_family: AgentFamily, target: DebateTarget,
    target_content: dict, winning_refinement: str,
) -> dict:
    """Dev override path: function_calling has the schema enforced API-side, no manual parse/repair needed."""
    schema = _REVISED_OUTPUT_SCHEMA[target]
    sys = (
        f"你的观点在辩论中被对方采纳。基于你的最终 refinement，"
        f"产出修订版 {target} 的结构化对象（严格遵守 required 字段与 enum 取值）。"
    )
    user = json.dumps(
        {"original": target_content, "winning_refinement": winning_refinement},
        ensure_ascii=False,
    )
    llm = get_llm(winner_family).with_structured_output(schema, method="function_calling")
    result = cast(BaseModel, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]))
    return result.model_dump()


def _finalize_via_json_object(
    winner_family: AgentFamily, target: DebateTarget,
    target_content: dict, winning_refinement: str,
) -> dict:
    """Normal three-family path: raw JSON + _repair_for_schema + Pydantic validate.
    with_structured_output has no hook for a repair step, so this uses bind(response_format) instead."""
    schema = _REVISED_OUTPUT_SCHEMA[target]
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
    sys = (
        f"你的观点在辩论中被对方采纳。基于你的最终 refinement，产出修订版 {target} 的 JSON 对象。\n\n"
        f"严格遵守以下 JSON Schema（required 字段不可缺失，enum 必须逐字匹配）：\n"
        f"{schema_json}\n\n输出纯 JSON，不加 markdown 包裹。"
    )
    user = json.dumps(
        {"original": target_content, "winning_refinement": winning_refinement},
        ensure_ascii=False,
    )
    llm = get_llm(winner_family).bind(response_format={"type": "json_object"})
    raw = cast(AIMessage, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]))
    raw_str = raw.content.strip()
    if raw_str.startswith("```"):
        parts = raw_str.split("```", 2)
        raw_str = parts[1].lstrip("json").strip() if len(parts) >= 3 else raw_str
    raw_dict = _repair_for_schema(json.loads(raw_str), target)
    return schema.model_validate(raw_dict).model_dump()


# ── main flow ───────────────────────────────────────────────────────────


def run_debate(
    target: DebateTarget,
    target_content: dict,
    seed_positions: dict[AgentFamily, DebatePosition],
    families: tuple[AgentFamily, AgentFamily] = ("deepseek", "gpt-5"),
    judge: AgentFamily = "doubao",
    max_rounds: int = 2,
) -> DebateResult:
    """Run the full debate and return a DebateResult.

    families = the 2 debaters, judge must differ from both. seed_positions are
    injected by the caller from real experience, so debaters aren't fabricating from
    nothing. max_rounds=2 bounds token cost.
    """
    if judge in families:
        raise ValueError(f"judge={judge!r} 不能与辩方 {families!r} 重叠")

    fam_a, fam_b = families
    pos_a = seed_positions[fam_a]
    pos_b = seed_positions[fam_b]
    rounds: list[DebateRound] = []

    for round_idx in range(1, max_rounds + 1):
        crit_a_on_b = _phase_critique(fam_a, pos_a, pos_b)
        crit_b_on_a = _phase_critique(fam_b, pos_b, pos_a)
        refined_a = _phase_refine(fam_a, pos_a, crit_b_on_a)
        refined_b = _phase_refine(fam_b, pos_b, crit_a_on_b)

        rounds.append(DebateRound(
            round=round_idx,
            positions=[pos_a, pos_b],
            critiques={fam_b: crit_a_on_b, fam_a: crit_b_on_a},
            refinements={fam_a: refined_a.refinement, fam_b: refined_b.refinement},
        ))

        # converges as soon as either side concedes, skipping the judge
        if not refined_a.still_disagrees or not refined_b.still_disagrees:
            winner = fam_a if refined_a.still_disagrees else fam_b
            winning = refined_a.refinement if refined_a.still_disagrees else refined_b.refinement
            return DebateResult(
                target=target, rounds=rounds,
                final_verdict="accepted_with_revision",
                judge_family=None,
                judge_rationale=f"self-converged at round {round_idx}",
                revised_output=_phase_finalize_converged(winner, target, target_content, winning),
            )

        # next round's position = this round's refinement
        if round_idx < max_rounds:
            pos_a = DebatePosition(agent_family=fam_a, claim=refined_a.refinement, evidence=pos_a.evidence)
            pos_b = DebatePosition(agent_family=fam_b, claim=refined_b.refinement, evidence=pos_b.evidence)

    return _phase_judge(judge, target, target_content, rounds)
