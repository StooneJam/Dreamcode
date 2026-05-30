"""reroute skill —— 事实性信号的根因分析 + 阶段回溯。

debate 的对称路径：AgentSignal.requires_debate=false 时触发。
"""
from __future__ import annotations

import json
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import gpt
from cca.schema import AgentSignal

RerouteTarget = str  # "phase_1" | "phase_2" | "phase_3"

_PHASE_FIELD = {
    "phase_1": "exploration_result",
    "phase_2": "task_plan",
    "phase_3": "report_task",
}

_SYSTEM_PROMPT = """你是竞品分析系统的纠偏 skill - reroute。
下游 Agent 报告了一个事实性问题（数据缺失/URL 失效/数据错误等），不涉及主观判断。
你的任务：诊断根因 + 决定回溯到哪个阶段。

## 三阶段语义
- phase_1 采集层：Collector 联网获取原始数据。回到此阶段会清空 exploration_result。
- phase_2 规划层：PM 基于已有采集结果制定 TaskPlan。回到此阶段不重采，只重排任务。
- phase_3 报告层：PM 给 Reporter 下发 ReportTask（focus_dimensions / sections / SWOT 范围）。
  采集+情感数据无误但报告任务不合理时回到此阶段。

## 决策规则
- 单产品数据缺失 / URL 失效 / 抓错 → phase_2
  （PM 重排 task_plan 加上缺失维度后 fanout 重采，不重做 exploration 以保留收敛过 debate 的 competitor_names）
- 产品虚假 / 停服 → phase_1
  （exploration 本身错，必须重做粗探索）
- exploration_result 大面积数据不可用 → phase_1
- 采集数据正确但 competitor_names / priority_dimensions / 任务分配有误 → phase_2
- ReviewUnit 已通过但 ReportTask 的 focus_dimensions / sections 数据不足 → phase_3
- 章节超出数据范围、SWOT 覆盖产品超出 profiles → phase_3
- 默认偏好 phase_2 重采集，避免重做 exploration 丢失已收敛信息

## Phase 2 bucket 覆盖规则
- 单产品某 bucket 缺失（qa_flags 含 `bucket_uncovered: X`）→ phase_2
  （PM 重排 task_plan，可能调整该产品的 priority_dimensions 引导 Collector 补采）
- 全产品都缺同一 bucket（多个 ReviewUnit 含同一 `bucket_uncovered: X`）→ phase_2
  并在 root_cause 明示 "PM 应调整 tentative_buckets 或 bucket_keywords"（提示 PM 该 bucket 本身可能设定不合理，应在 phase_2 重生成 TaskPlan 时调整定义而非反复重采）
- bucket 覆盖问题永不回 phase_1（这是任务规划层的语义聚类问题，不是采集层问题）
"""


class RerouteDecision(BaseModel):
    """reroute 输出：根因诊断 + 回溯指令。"""

    target_phase: RerouteTarget = Field(
        description="回溯阶段 phase_1 / phase_2 / phase_3，含义见 system prompt 中决策规则"
    )
    root_cause: str = Field(description="根因分析，一句话")
    fix_summary: dict = Field(
        description="修正建议，key=需修改字段名，value=修正内容或方向"
    )
    rationale: str = Field(description="为什么回溯到该阶段而非其他阶段")


def reroute(signal: AgentSignal, state_json: str) -> RerouteDecision:
    """分析事实性信号，输出回溯决策。state_json 为 state 的最小切片快照。"""
    # method="function_calling" 显式指定，绕开 langchain-openai 0.3+ 默认 json_schema strict mode。
    # strict mode 要求 dict 字段显式 additionalProperties=false，RerouteDecision.fix_summary 是裸 dict，
    # 会被 strict mode 拒（400 BadRequest）。与 pm._invoke_pm 同样模式。
    llm = gpt.with_structured_output(RerouteDecision, method="function_calling")
    user = json.dumps({"signal": signal.model_dump(), "state": state_json}, ensure_ascii=False)
    return cast(
        RerouteDecision,
        llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user)]),
    )


def apply_reroute(decision: RerouteDecision) -> dict:
    """reroute 决策 → state 更新 dict。"""
    updates: dict = {}
    if field := _PHASE_FIELD.get(decision.target_phase):
        updates[field] = None
    updates["audit_log"] = [{"agent": "reroute", "decision": decision.model_dump()}]
    return updates


def apply_reroute_phase(target_phase: RerouteTarget) -> dict:
    """已知目标阶段时直接产 state 更新，跳过 LLM 诊断。

    review_node 预检产的 data_gap 根因恒为 phase_2，无需再调一次 reroute LLM。
    """
    updates: dict = {}
    if field := _PHASE_FIELD.get(target_phase):
        updates[field] = None
    updates["audit_log"] = [{
        "agent": "reroute", "auto_phase": target_phase,
        "note": "已知根因，跳过 LLM 诊断",
    }]
    return updates
