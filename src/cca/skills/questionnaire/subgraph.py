"""Questionnaire skill entry point -- design -> distribute -> collect -> anonymize -> return the aggregated result."""
from __future__ import annotations

from cca.settings import load_config
from cca.skills.questionnaire.anonymize import anonymize_responses
from cca.skills.questionnaire.collect import collect_responses, get_or_create_questionnaire
from cca.skills.questionnaire.distribute import format_questionnaire


def run_questionnaire_skill(
    product_name: str,
    competitor_names: list[str],
    dimensions: list[str],
    n_responses: int | None = None,
    fill_mode: str | None = None,
) -> dict:
    """The full questionnaire flow, supporting cache reuse and real/LLM fill modes.

    Returns a dict:
        questionnaire_display  -- the formatted questionnaire text (for the frontend)
        fill_mode              -- the fill mode actually used
        responses              -- anonymized answer list, for Insight Agent's NLP analysis

    Side effect: in LLM mode, answers are persisted to SQLite store.db; questionnaires are cached by product name.
    """
    cfg = load_config().get("questionnaire", {})
    if fill_mode is None:
        fill_mode = cfg.get("fill_mode", "llm")
    if n_responses is None:
        n_responses = cfg.get("n_llm_responses", 5)

    questionnaire = get_or_create_questionnaire(product_name, competitor_names, dimensions)
    display = format_questionnaire(questionnaire)
    raw = collect_responses(questionnaire, n=n_responses, fill_mode=fill_mode)
    clean = anonymize_responses(raw) if raw else []

    return {
        "questionnaire_display": display,
        "fill_mode": fill_mode,
        "responses": [
            {"respondent_id": r.respondent_id, "answers": [a.model_dump() for a in r.answers]}
            for r in clean
        ],
    }
