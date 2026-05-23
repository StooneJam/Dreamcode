"""
跨家族 debate skill。

应用 checkpoint：
    1. PM 二轮 TaskPlan 校验
    2. Analyst SWOT 校验
    3. Report 终审（call_report_reviewer skill 内部调用）

流程：caller 注入 seed_positions → Critique → Refine → 任一方让步即收敛，否则Judge 仲裁。
仲裁方必须异于两个辩方，三家族零重叠。
"""
from __future__ import annotations
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import get_llm
from cca.schema import AgentFamily, DebatePosition, DebateResult, DebateRound

DebateTarget = Literal["pm_taskplan", "analyst_swot", "report"]


# 是否认可对方观点。
class _Refinement(BaseModel):
    text: str
    still_disagrees: bool = Field(
        description="经过本轮修订后，你是否仍与对方在核心 claim 上有分歧"
    )

# 单方/单轮的轻量结构化输出类型
class _Critique(BaseModel):
    text: str = Field(description="对对方观点的具体批驳，至少指出 1 处问题")


# 3阶段实现

def _phase_critique(
    family: AgentFamily,
    my_position: DebatePosition,
    other_position: DebatePosition,
) -> str:
    """阶段 1：看到对方观点后写 critique。"""
    llm = get_llm(family).with_structured_output(_Critique, method="json_mode")
    sys = (
        f"你是 {family} 家族。请针对 {other_position.agent_family} 的观点写出批驳。"
        "聚焦事实层面：哪些 claim 不成立？哪些 evidence 太弱或缺失？"
        "不要泛泛而谈，每条批驳指向对方原文具体段落。"
    )
    user = json.dumps(
        {
            "my_position": my_position.model_dump(),
            "other_position": other_position.model_dump(),
        },
        ensure_ascii=False,
    )
    return llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]).text


def _phase_refine(
    family: AgentFamily,
    my_position: DebatePosition,
    other_critique: str,
) -> _Refinement:
    """阶段 2：基于对方 critique 修订自己观点。"""
    llm = get_llm(family).with_structured_output(_Refinement, method="json_mode")
    sys = (
        f"你是 {family} 家族。基于对方对你的批驳，修订你原来的观点。"
        "可选："
        "(a) 维持原 claim 并加强 evidence"
        "(b) 部分修订 claim"
        "(c) 撤回 claim 接受批驳"
        "明确说明你的选择以及理由。"
    )
    user = json.dumps(
        {"my_position": my_position.model_dump(), "critique_from_other": other_critique},
        ensure_ascii=False,
    )
    return llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)])


def _phase_judge(
    judge: AgentFamily,
    target: DebateTarget,
    target_content: dict,
    rounds: list[DebateRound],
) -> DebateResult:
    """阶段 3：辩论未自然收敛，引入第三家族仲裁，必须异于两个辩方。"""
    llm = get_llm(judge).with_structured_output(DebateResult, method="json_mode")
    sys = (
        f"你是 {judge} 家族的独立仲裁者。两个辩方已对 {target} 完成 {len(rounds)} 轮辩论。"
        "综合最后一轮的 refinements，请pick你认为的 final_verdict："
        "accepted（采纳原内容）/ rejected（拒绝原内容）/ "
        "accepted_with_revision（部分采纳，给出修订版 revised_output）。"
        "判断只看事实是否站得住，不偏袒任一辩方。"
    )
    user = json.dumps(
        {
            "target": target,
            "target_content": target_content,
            "rounds": [r.model_dump() for r in rounds],
        },
        ensure_ascii=False,
    )
    result = llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)])
    # judge_family 由代码强制覆盖，防止 LLM 自报错家族
    result.judge_family = judge
    result.target = target
    result.rounds = rounds
    return result


# debate结果整理，发送给PM
def _phase_finalize_converged(
    winner_family: AgentFamily,
    target: DebateTarget,
    target_content: dict,
    winning_refinement: str,
) -> dict:
    """获胜方把共识结构化为修订版 target_content。"""
    llm = get_llm(winner_family)
    sys = (
        f"你的观点在辩论中被对方采纳。请基于你的最终 refinement，"
        f"产出修订版 {target}，结构与原 target_content 一致。"
    )
    user = json.dumps(
        {"original": target_content, "winning_refinement": winning_refinement},
        ensure_ascii=False,
    )
    response = llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)])
    raw = response.content if hasattr(response, "content") else str(response)
    return json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())


# debate 主流程


def run_debate(
    target: DebateTarget,
    target_content: dict,
    families: tuple[AgentFamily, AgentFamily] = ("deepseek", "gpt-5"),
    judge: AgentFamily = "doubao",
    max_rounds: int = 2,
    seed_positions: dict[AgentFamily, DebatePosition] | None = None,
) -> DebateResult:
    """
    跑完整 3 阶段 debate，返回 DebateResult。
    families 是 2 个辩方，judge 必须与两者均不同。
    max_rounds 控制循环次数，考虑token消耗部分，默认为 2。
    seed_positions 采用 caller 注入 Agent 的真实经验作为初始 position；
    例如 Collector 把采集数据封装为 DebatePosition.evidence，避免辩方凭空生成。
    """
    if judge in families:
        raise ValueError(f"judge={judge!r} 不能与辩方 {families!r} 重叠")

    fam_a, fam_b = families
    seed = seed_positions or {}
    rounds: list[DebateRound] = []

    # 第一轮初始 position — caller 注入
    pos_a = seed.get(fam_a) 
    pos_b = seed.get(fam_b)

    for round_idx in range(1, max_rounds + 1):
        crit_a_on_b = _phase_critique(fam_a, pos_a, pos_b)
        crit_b_on_a = _phase_critique(fam_b, pos_b, pos_a)
        refined_a = _phase_refine(fam_a, pos_a, crit_b_on_a)
        refined_b = _phase_refine(fam_b, pos_b, crit_a_on_b)

        rounds.append(
            DebateRound(
                round=round_idx,
                positions=[pos_a, pos_b],
                critiques={fam_b: crit_a_on_b, fam_a: crit_b_on_a},
                refinements={fam_a: refined_a.text, fam_b: refined_b.text},
            )
        )

        # 短路，跳过 judge 阶段，debate提前收敛，返回debate结果给PM
        if not refined_a.still_disagrees or not refined_b.still_disagrees:
            return DebateResult(
                target=target,
                rounds=rounds,
                final_verdict="accepted_with_revision",
                judge_family=None,               
                judge_rationale=f"self-converged at round {round_idx}: both parties accepted other's position",
                revised_output=_phase_finalize_converged(
                    winner_family=fam_a if refined_a.still_disagrees else fam_b,
                    target=target,
                    target_content=target_content,
                    winning_refinement=refined_a.text if refined_a.still_disagrees else refined_b.text
                ),              
            )
    
        # 下一轮的 position = 本轮 refinement
        if round_idx < max_rounds:
            pos_a = DebatePosition(
                agent_family=fam_a, claim=refined_a.text, evidence=pos_a.evidence
            )
            pos_b = DebatePosition(
                agent_family=fam_b, claim=refined_b.text, evidence=pos_b.evidence
            )

    return _phase_judge(judge, target, target_content, rounds)
