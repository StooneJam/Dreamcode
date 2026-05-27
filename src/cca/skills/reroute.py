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
- 数据缺失 / URL 失效 / 抓错 → phase_1
- 产品虚假 / 停服 → phase_1
- exploration_result 大面积数据不可用 → phase_1
- 采集数据正确但 competitor_names / priority_dimensions / 任务分配有误 → phase_2
- ReviewUnit 已通过但 ReportTask 的 focus_dimensions / sections 数据不足 → phase_3
- 章节超出数据范围、SWOT 覆盖产品超出 profiles → phase_3
- 能定位到采集层的优先 phase_1，避免基于脏数据反复返工
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
    llm = gpt.with_structured_output(RerouteDecision)
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
