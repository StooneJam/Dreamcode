"""Questionnaire design -- auto-generates a survey from a product, its competitors, and analysis dimensions."""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import get_llm
from cca.llm.structured import invoke_structured

_SYS = (
    "You are a survey design expert. Generate 6-8 user survey questions based on the "
    "product info, mixing rating_5 (5-point scale), multiple_choice (single select), "
    "and open_text (free response). Each question needs a unique id (q1, q2...); "
    "multiple_choice must provide an options list (3-5 options). Focus questions on "
    "real user experience, don't ask for personal information."
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
    """Use the LLM to generate a user survey targeting the product and its competitors."""
    user = json.dumps(
        {"product_name": product_name, "competitor_names": competitor_names, "focus_dimensions": dimensions},
        ensure_ascii=False,
    )
    return invoke_structured(
        get_llm("deepseek"),
        [SystemMessage(content=_SYS), HumanMessage(content=user)],
        Questionnaire,
    )
