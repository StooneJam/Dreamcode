"""Questionnaire distribution -- formats a Questionnaire into readable text for the frontend or logs."""
from __future__ import annotations

from cca.skills.questionnaire.design import Questionnaire

_TYPE_LABEL = {
    "rating_5": "（1-5 分量表）",
    "multiple_choice": "（单选题）",
    "open_text": "（开放作答）",
}


def format_questionnaire(q: Questionnaire) -> str:
    """Render a Questionnaire object as plain text, for showing to the user."""
    lines = [
        f"=== 用户调研问卷：{q.product_name} ===",
        f"参考竞品：{', '.join(q.competitor_names)}",
        "",
    ]
    for idx, question in enumerate(q.questions, 1):
        label = _TYPE_LABEL.get(question.q_type, "")
        lines.append(f"{idx}. [{question.id}] {question.text} {label}")
        for opt in question.options:
            lines.append(f"   [ ] {opt}")
        lines.append("")
    lines.append("=" * 40)
    return "\n".join(lines)
