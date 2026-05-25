"""问卷设计 —— 基于产品、竞品、分析维度自动生成调查问卷。"""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import deepseek
from cca.llm.structured import invoke_structured

_SYS = (
    "你是问卷设计专家。根据产品信息生成 6-8 道用户调查题，"
    "类型混合使用 rating_5（5分量表）、multiple_choice（单选）、open_text（开放作答）。"
    "每题有唯一 id（q1, q2...）；multiple_choice 必须提供 options 列表（3-5 个选项）。"
    "题目聚焦用户真实体验，不询问个人信息。"
)


class Question(BaseModel):
    id: str
    text: str
    q_type: Literal["rating_5", "multiple_choice", "open_text"]
    options: list[str] = Field(default_factory=list)


class Questionnaire(BaseModel):
    product_name: str
    competitor_names: list[str]
    questions: list[Question]


def design_questionnaire(
    product_name: str,
    competitor_names: list[str],
    dimensions: list[str],
) -> Questionnaire:
    """用 LLM 生成针对产品与竞品的用户调查问卷。"""
    user = json.dumps(
        {"product_name": product_name, "competitor_names": competitor_names, "focus_dimensions": dimensions},
        ensure_ascii=False,
    )
    return invoke_structured(
        deepseek,
        [SystemMessage(content=_SYS), HumanMessage(content=user)],
        Questionnaire,
    )
