"""问卷 skill 入口 —— design → distribute → collect → anonymize → 返回汇总结果。"""
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
    """完整问卷流程，支持缓存复用和真实/LLM 两种填写模式。

    返回 dict：
        questionnaire_display  — 格式化后的问卷文本（供前端展示）
        fill_mode              — 实际使用的填写模式
        responses              — 匿名化回答列表，供 Insight Agent NLP 分析

    副作用：LLM 模式下回答持久化到 SQLite store.db；问卷按产品名缓存。
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
