"""
reroute skill —— 事实性信号的根因分析与阶段回溯。

对应 debate 的对称路径：AgentSignal.requires_debate=false 时触发。
诊断信号根因，决定回溯到 PM 哪个阶段、修什么字段。
"""
from __future__ import annotations

import json
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import gpt
from cca.schema import AgentSignal

RerouteTarget = str  # "phase_1" | "phase_2" | "phase_3" | "phase_4"


class RerouteDecision(BaseModel):
    """reroute 输出：根因诊断 + 回溯指令。"""

    target_phase: RerouteTarget = Field(
        description=(
            "回溯到的阶段。"
            "phase_1=Collector 重新联网采集（数据缺失/抓错/停服/URL 失效/置信度极低）"
            "phase_2=PM 重新制定 TaskPlan（竞品列表/维度优先级/任务分配有误）"
            "phase_3=PM 重新制定 AnalystTask（focus_dimensions 不可用）"
            "phase_4=PM 重新制定 ReportTask（章节/格式调整）"
        )
    )
    root_cause: str = Field(description="根因分析，一句话说明问题出在哪个环节")
    fix_summary: dict = Field(description="修正建议，key 为需修改的字段名，value 为修正内容或修正方向")
    rationale: str = Field(description="为什么回溯到该阶段而非其他阶段")


def reroute(signal: AgentSignal, state_json: str) -> RerouteDecision:
    """分析事实性信号，输出回溯决策。

    signal: 下游 Agent 发来的信号
    state_json: 当前 state 的 JSON 快照（profiles / review_state / 各阶段 task 等）
    """
    llm = gpt.with_structured_output(RerouteDecision)

    sys = (
        "你是竞品分析系统的纠偏 skill- reroute。"
        "下游 Agent 报告了一个事实性问题（数据缺失、字段不可采集、URL 失效、数据错误等），"
        "不涉及主观判断分歧。你的任务是诊断根因并决定回溯到哪个阶段。"

        "## 阶段 1 vs 阶段 2 的核心区别"

        "阶段 1 是采集层——Collector 联网获取原始数据。如果信号指向采集阶段出了事实性问题，"
        "应回到阶段 1，清除已有 exploration_result 强制 Collector 重新探索。"

        "阶段 2 是规划层——PM 基于 Collector 已有采集结果制定 TaskPlan。"
        "如果采集数据本身无误，只是 PM 的竞品选择、维度优先级、任务分配有误，"
        "则回到阶段 2，PM 重新生成 TaskPlan，不需要 Collector 重采。"

        "## 决策规则"
        "- 数据缺失、URL 失效、抓取到错误数据 → phase_1"
        "- 产品虚假、已确认停服或不再运营 → phase_1"
        "- 当前 exploration_result 中数据置信度极低、大面积数据不可用 → phase_1"
        "- 采集数据正确，但 PM 给的 competitor_names / priority_dimensions / 任务分配有误 → phase_2"
        "- Collector 和 Insight 的输出经 ReviewUnit 验证通过，但 AnalystTask 指定的 focus_dimensions"
        "- 因数据不足无法支撑分析 → phase_3"
        "- 报告层面问题，如指定章节数据不足或章节顺序不合理 → phase_4"
        "- 能定位到采集层的优先回到阶段 1，避免基于脏数据反复返工"
    )

    user = json.dumps(
        {"signal": signal.model_dump(), "state": state_json},
        ensure_ascii=False,
    )
    result = cast(RerouteDecision, llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]))
    return result


def apply_reroute(decision: RerouteDecision, state: dict) -> dict:
    """根据 reroute 决策更新 state 中的对应字段。

    返回需要更新的 state 字段 dict，调用方 merge 回 graph state。
    """
    updates: dict = {}

    if decision.target_phase == "phase_1":
        updates["exploration_result"] = None

    elif decision.target_phase == "phase_2":
        updates["task_plan"] = None

    elif decision.target_phase == "phase_3":
        updates["analyst_task"] = None

    elif decision.target_phase == "phase_4":
        updates["report_task"] = None

    updates["audit_log"] = [{
        "agent": "reroute",
        "decision": decision.model_dump(),
    }]
    return updates
