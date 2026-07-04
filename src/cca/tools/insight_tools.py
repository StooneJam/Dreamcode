"""Insight-specific @tools: questionnaire / finalize_sentiment / record_key_events / challenge_pm."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from cca.schema import AgentSignal, ChallengePayload, Fact, UserSentiment
from cca.skills.questionnaire.subgraph import run_questionnaire_skill
from cca.tools._validation import repair_llm_json, safe_load_list, safe_load_validate
from cca.tools.appstore import scrape_app_store  # noqa: F401 — re-exported as agent tool


@tool
def run_questionnaire(product_name: str, competitor_names: str, dimensions: str) -> str:
    """Design and collect a user questionnaire (with SQLite caching).

    Args:
        competitor_names: comma-separated, e.g. "DingTalk,WeCom"
        dimensions: comma-separated, e.g. "collaboration,pricing,stability"
    """
    result = run_questionnaire_skill(
        product_name=product_name,
        competitor_names=[n.strip() for n in competitor_names.split(",") if n.strip()],
        dimensions=[d.strip() for d in dimensions.split(",") if d.strip()],
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def finalize_sentiment(product_name: str, sentiment_json: str) -> str:
    """Submit a single product's UserSentiment (sentiment_json is a JSON string matching the schema).

    Shape: {"positive_themes": ["theme1","theme2"], "negative_themes": [...],
          "aggregate_rating": 4.2, "rating_review_count": 1000, "rating_source": "google_maps",
          "representative_reviews": [{"text": "original text", "rating": 4, "platform": "dianping"}],
          "sources": [{"source_url": "https://..."}]}
    positive_themes / negative_themes are **string arrays** (don't fill in a single
    delimiter-separated string); each sources[] item is **an object with
    source_url** (don't fill in a bare URL string).
    """
    sentiment, err = safe_load_validate(
        sentiment_json, UserSentiment,
        pre_clean=repair_llm_json,
        hint=(
            "字段规则提示："
            "\n- positive_themes / negative_themes 必填字符串数组，如 [\"性价比高\",\"出餐快\"]"
            "\n- aggregate_rating 可选，浮点 1.0–5.0（渠道聚合评分，App / 电商 / 垂类皆可）"
            "\n- rating_review_count 可选整数；rating_source 可选字符串（来源渠道名，如 'appstore_cn'/'tmall'/'jd'）"
            "\n- sources[] 每项是对象且含 source_url，如 [{\"source_url\":\"https://...\"}]"
            "\n- representative_reviews[].rating 可选，整数 1–5；platform 开放字符串，未知填 'other'"
        ),
    )
    if err:
        return err
    return json.dumps(
        {"product_name": product_name, "sentiment": sentiment.model_dump()},
        ensure_ascii=False,
    )


@tool
def record_key_events(product_name: str, events_json: str | list) -> str:
    """Record a single product's material events and business conflicts/interest
    disputes, for Report to draw causal conclusions from.

    events_json: a JSON array of Fact objects (passed in as one JSON string). Each Fact:
      {"statement": "objective factual statement (no causal interpretation)",
       "evidence": [{"source_url": "https://...", "snippet": "original excerpt (optional)"}]}
    statement is required; evidence needs at least 1 entry, **each an object with
    source_url** (don't fill in a bare URL string).
    Example: [{"statement": "HQ pushed a $1 promo drink to drive traffic; multiple
            franchisees said they lose money per cup and refused to comply",
            "evidence": [{"source_url": "https://news.example.com/a"}]}]
    """
    # Doubao sometimes passes an array directly instead of a JSON string; normalize
    # by serializing, then use lenient parsing + structural repair (fewer retries)
    if not isinstance(events_json, str):
        events_json = json.dumps(events_json, ensure_ascii=False)
    events, err = safe_load_list(events_json, Fact, pre_clean=repair_llm_json)
    if err:
        return err
    return json.dumps(
        {"product_name": product_name, "key_events": [e.model_dump() for e in events]},
        ensure_ascii=False,
    )


@tool
def challenge_pm(
    claim: str,
    evidence: list[str],
    suggested_fix: str | None = None,
    requires_debate: bool = False,
) -> str:
    """Challenge PM's TaskPlan. Pass requires_debate=False for factual errors (e.g.
    product doesn't exist), True for subjective disagreements (audience/dimension
    objections). evidence needs at least 1 entry."""
    signal = AgentSignal(
        from_agent="insight", kind="pm_challenge", target="task_plan",
        payload=ChallengePayload(claim=claim, evidence=evidence, suggested_fix=suggested_fix),
        requires_debate=requires_debate,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()
