"""问卷匿名化 —— 正则脱敏 open_text 回答中的 PII。"""
from __future__ import annotations

import re

from cca.skills.questionnaire.collect import QuestionResponse, SurveyResponse

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}"), "[邮箱]"),
    (re.compile(r"\d{17}[\dXx]"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{6}(?!\d)"), "[邮编]"),
]


def _scrub(text: str) -> str:
    for pattern, placeholder in _RULES:
        text = pattern.sub(placeholder, text)
    return text


def anonymize_responses(responses: list[SurveyResponse]) -> list[SurveyResponse]:
    """对回答做 PII 脱敏，respondent_id 截断为前 8 位匿名标识。"""
    return [
        SurveyResponse(
            respondent_id=f"anon_{resp.respondent_id[:8]}",
            product_name=resp.product_name,
            answers=[
                QuestionResponse(question_id=a.question_id, answer=_scrub(a.answer))
                for a in resp.answers
            ],
        )
        for resp in responses
    ]
