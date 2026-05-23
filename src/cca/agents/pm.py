"""
PM Agent —— 分阶段规划、下发指令、评审下游产出。

不是 ReAct agent，没有工具，纯结构化规划 + 评审。
4 个阶段函数对应 pm.md 的 4 个阶段。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from cca.llm.factory import gpt
from cca.schema import (
    AnalystTask,
    InitialBrief,
    ReportTask,
    TaskPlan,
)
from cca.state import CCAState

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "pm.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _phase_prefix(phase: str) -> str:
    """标注当前阶段，让 LLM 在完整 prompt 中定位到对应阶段规则。"""
    return f"## 当前阶段：{phase}\n\n"


def initial_brief_node(state: CCAState) -> dict:
    """阶段一：凭训练知识起草 InitialBrief。"""
    llm = gpt.with_structured_output(InitialBrief)
    user = _phase_prefix("阶段一 InitialBrief") + json.dumps(
        {"user_query": state["user_query"]},
        ensure_ascii=False,
    )
    result = cast(InitialBrief, llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]))
    return {"initial_brief": result.model_dump()}


def task_plan_node(state: CCAState) -> dict:
    """阶段二：基于 CollectorExplorationResult 创建 TaskPlan。"""
    llm = gpt.with_structured_output(TaskPlan)
    user = _phase_prefix("阶段二 TaskPlan") + json.dumps(
        {
            "user_query": state["user_query"],
            "exploration_result": state.get("exploration_result", {}),
            "competitor_names": state.get("competitor_names", []),
        },
        ensure_ascii=False,
    )
    result = cast(TaskPlan, llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]))
    return {
        "task_plan": result.model_dump(),
        "competitor_names": result.competitor_names,
    }


def analyst_task_node(state: CCAState) -> dict:
    """阶段三：基于 profiles 创建 AnalystTask。"""
    llm = gpt.with_structured_output(AnalystTask)
    user = _phase_prefix("阶段三 AnalystTask") + json.dumps(
        {
            "user_query": state["user_query"],
            "target_product": state["target_product"],
            "competitor_names": state.get("competitor_names", []),
            "profiles": state.get("profiles", {}),
        },
        ensure_ascii=False,
    )
    result = cast(AnalystTask, llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]))
    return {"analyst_task": result.model_dump()}


def report_task_node(state: CCAState) -> dict:
    """阶段四：基于 SWOT 创建 ReportTask。"""
    llm = gpt.with_structured_output(ReportTask)
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
    result = cast(ReportTask, llm.invoke([SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]))
    return {"report_task": result.model_dump()}
