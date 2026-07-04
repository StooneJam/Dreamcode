"""Tests for collector_tools: finalize_exploration's schema validation, challenge_pm's AgentSignal construction."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError


def test_finalize_exploration_accepts_valid_schema() -> None:
    from cca.tools.collector_tools import finalize_exploration

    valid = json.dumps({
        "target_product": "飞书",
        "product_type": "企业协作平台",
        "competitor_names": ["钉钉", "企业微信"],
        "discovered_dimensions": ["视频会议", "定价"],
        "initial_profiles": [
            {"product_name": "钉钉", "company": "阿里巴巴"},
        ],
        "rationale": "钉钉、企业微信为同类协作平台",
    })

    output = finalize_exploration.invoke({"result_json": valid})
    parsed = json.loads(output)
    assert parsed["target_product"] == "飞书"
    assert parsed["competitor_names"] == ["钉钉", "企业微信"]
    assert parsed["rationale"].startswith("钉钉")


def test_finalize_exploration_returns_error_on_missing_required_field() -> None:
    """Missing required fields like competitor_names -> returns an LLM-friendly error string (doesn't raise)."""
    from cca.tools.collector_tools import finalize_exploration

    invalid = json.dumps({"target_product": "飞书"})  # missing product_type / competitor_names / ...
    result = finalize_exploration.invoke({"result_json": invalid})
    assert "CollectorExplorationResult 校验失败" in result


def test_challenge_pm_constructs_collector_signal() -> None:
    from cca.tools.collector_tools import challenge_pm

    output = challenge_pm.invoke({
        "claim": "目标产品 X 已停服 6 个月",
        "evidence": ["官网 404", "应用商店下架"],
        "suggested_fix": "请用户重选 target_product",
        "requires_debate": False,
    })
    signal = json.loads(output)
    assert signal["from_agent"] == "collector"
    assert signal["target"] == "initial_brief"
    assert signal["kind"] == "pm_challenge"
    assert signal["payload"]["claim"] == "目标产品 X 已停服 6 个月"
    assert len(signal["payload"]["evidence"]) == 2
    assert signal["payload"]["suggested_fix"] == "请用户重选 target_product"
    assert signal["requires_debate"] is False
    assert "signal_id" in signal


def test_challenge_pm_rejects_empty_evidence() -> None:
    """ChallengePayload enforces evidence min_length=1; a zero-evidence challenge is rejected."""
    from cca.tools.collector_tools import challenge_pm

    with pytest.raises(ValidationError):
        challenge_pm.invoke({"claim": "X 不对", "evidence": []})


def test_challenge_pm_requires_debate_flag_propagates() -> None:
    from cca.tools.collector_tools import challenge_pm

    output = challenge_pm.invoke({
        "claim": "PM 选的产品不合理",
        "evidence": ["市场份额不到 1%"],
        "requires_debate": True,
    })
    signal = json.loads(output)
    assert signal["requires_debate"] is True


# ── Phase 2 tools ────────────────────────────────────────────────────


def _valid_profile_json(product_name: str = "钉钉") -> str:
    """Build the minimal JSON that passes ProductProfile validation."""
    return json.dumps({
        "product_name": product_name,
        "company": "阿里巴巴",
        "product_type": "企业协作平台",
        "target_users": "中大型企业",
        "website": "https://www.dingtalk.com",
        "dimensions": [],
        "pricing": None,
        "sources": [],
    }, ensure_ascii=False)


def _finalize(product_name: str, profile_json: str):
    """Invoke in ToolCall form, getting back a ToolMessage with .artifact (content only shows the model a stop instruction)."""
    from cca.tools.collector_tools import finalize_profile

    return finalize_profile.invoke({
        "type": "tool_call", "name": "finalize_profile",
        "args": {"product_name": product_name, "profile_json": profile_json}, "id": "t1",
    })


def test_finalize_profile_accepts_valid_schema() -> None:
    msg = _finalize("钉钉", _valid_profile_json("钉钉"))
    assert "提交成功" in msg.content
    assert msg.artifact["profile"]["company"] == "阿里巴巴"
    assert msg.artifact["profile"]["website"] == "https://www.dingtalk.com"


def test_finalize_profile_content_tells_model_to_stop() -> None:
    """The model only sees content: it must be a success+stop instruction, never
    echoing back the profile JSON (guards against the 859da7c infinite-loop regression)."""
    from cca.tools.collector_tools import finalize_profile

    content = finalize_profile.invoke({  # invoke(dict) 返回 content 字符串本身
        "product_name": "钉钉", "profile_json": _valid_profile_json("钉钉"),
    })
    assert isinstance(content, str)
    assert "不得再次调用 finalize_profile" in content


def test_finalize_profile_overrides_mismatched_product_name() -> None:
    """The product_name inside profile_json disagrees with the argument -> the argument wins (guards against LLM typos)."""
    msg = _finalize("钉钉", _valid_profile_json("DingTalk"))  # mismatched
    assert msg.artifact["profile"]["product_name"] == "钉钉"


def test_finalize_profile_returns_error_string_on_invalid_schema() -> None:
    """When schema validation fails, returns an error string (doesn't raise), so the
    LLM sees the ToolMessage and self-corrects.

    Raising inside create_react_agent would abort the ReAct loop, hence the return-value path.
    """
    from cca.tools.collector_tools import finalize_profile

    invalid = json.dumps({"product_name": "X", "product_type": 12345})  # wrong type
    result = finalize_profile.invoke({"product_name": "X", "profile_json": invalid})
    assert "ProductProfile 校验失败" in result
    assert "字段规则提示" in result


def test_finalize_profile_cleans_evidence_missing_source_url() -> None:
    """Evidence missing source_url is a common LLM mistake; this tool should drop it, not block the whole product."""
    raw = {
        "product_name": "Y",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "d1", "category": "功能",
            "facts": [
                {"statement": "完整", "evidence": [{"source_url": "https://ok.com", "snippet": "a"}]},
                {"statement": "evidence 缺 url", "evidence": [{"snippet": "b"}]},
            ],
        }],
        "sources": [
            {"source_url": "https://ok.com"},
            {"snippet": "no url"},  # should be dropped
        ],
    }
    profile = _finalize("Y", json.dumps(raw)).artifact["profile"]
    assert len(profile["dimensions"][0]["facts"]) == 1  # the fact missing url is dropped
    assert len(profile["sources"]) == 1                 # the sources entry missing url is dropped


def test_finalize_profile_keeps_dimensions_when_category_missing() -> None:
    """After relaxing: a dimension missing category (the culprit behind this incident's data loss) no longer wipes out the whole dimensions block; it's stored as-is."""
    raw = {
        "product_name": "W",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "AI",  # category deliberately omitted
            "facts": [{"statement": "F", "evidence": [{"source_url": "https://a.com"}]}],
        }],
    }
    msg = _finalize("W", json.dumps(raw))
    assert "提交成功" in msg.content
    assert len(msg.artifact["profile"]["dimensions"]) == 1     # the dimension is kept, no longer lost
    assert msg.artifact["profile"]["dimensions"][0]["category"] == ""


def test_finalize_profile_normalizes_fact_text_under_any_key() -> None:
    """The model puts a fact's body under any non-statement key
    (content/value/snippet/an unseen key) -> the longest string is taken and
    normalized into statement, preserving the body instead of losing it. Doesn't
    rely on an alias whitelist, so it generalizes across products."""
    long = "这是一段足够长的事实正文描述用于被识别为 statement"
    raw = {
        "product_name": "V",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "AI", "category": "功能",
            "facts": [
                {"content": f"content {long}", "evidence": [{"source_url": "https://a.com"}]},
                {"value": f"value {long}", "evidence": [{"source_url": "https://b.com"}]},
                {"snippet": f"snippet {long}", "evidence": [{"source_url": "https://c.com"}]},
                {"某个没见过的key": f"novel {long}", "evidence": [{"source_url": "https://d.com"}]},
            ],
        }],
    }
    profile = _finalize("V", json.dumps(raw)).artifact["profile"]
    facts = profile["dimensions"][0]["facts"]
    assert len(facts) == 4                                  # all 4 survive, none dropped as an empty fact
    assert all(long in f["statement"] for f in facts)       # the body under any key is normalized back into statement


def test_finalize_profile_coerces_invalid_pricing_model() -> None:
    """After relaxing: an invalid pricing_model is normalized to unknown, and the whole pricing block is kept instead of stripped."""
    raw = {
        "product_name": "W",
        "product_type": "SaaS",
        "pricing": {"has_free_tier": True, "pricing_model": "非法枚举值"},
    }
    msg = _finalize("W", json.dumps(raw))
    assert "提交成功" in msg.content
    assert msg.artifact["profile"]["pricing"]["pricing_model"] == "unknown"


def test_request_product_replacement_constructs_data_gap_signal() -> None:
    from cca.tools.collector_tools import request_product_replacement

    output = request_product_replacement.invoke({
        "product_name": "某幽灵产品",
        "reason": "官网 404，应用商店零搜索结果",
        "evidence": [
            "https://example.com/ghost-product 返回 404",
            "App Store 中文区搜索『某幽灵产品』命中 0 条",
        ],
    })
    signal = json.loads(output)
    assert signal["from_agent"] == "collector"
    assert signal["kind"] == "data_gap"
    assert signal["target"] == "task_plan"
    assert signal["requires_debate"] is False
    assert "某幽灵产品" in signal["payload"]["claim"]
    assert "404" in signal["payload"]["claim"]
    assert len(signal["payload"]["evidence"]) == 2
    assert "移除 某幽灵产品" in signal["payload"]["suggested_fix"]


def test_request_product_replacement_rejects_empty_evidence() -> None:
    """ChallengePayload enforces evidence min_length=1; empty evidence should be rejected."""
    from cca.tools.collector_tools import request_product_replacement

    with pytest.raises(ValidationError):
        request_product_replacement.invoke({
            "product_name": "X",
            "reason": "无理由",
            "evidence": [],
        })


def test_finalize_profile_autofills_sources_from_evidence() -> None:
    """When the LLM omits top-level sources, the tool should auto-aggregate URLs from dimensions/pricing's evidence.
    An R4 fallback: doesn't rely on the LLM remembering."""

    raw = {
        "product_name": "Z",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "AI能力", "category": "功能",
            "facts": [
                {"statement": "F1", "evidence": [{"source_url": "https://a.com", "snippet": "x"}]},
                {"statement": "F2", "evidence": [{"source_url": "https://b.com", "snippet": "y"}]},
            ],
        }],
        "pricing": {
            "has_free_tier": True, "pricing_model": "per_user",
            "tiers": [{
                "name": "Pro", "price_per_user_monthly": 10.0,
                "source": {"source_url": "https://c.com/pricing", "snippet": "$10"},
            }],
        },
        "sources": [],  # <- omitted by the LLM, the tool should backfill it
    }
    profile = _finalize("Z", json.dumps(raw)).artifact["profile"]
    urls = {s["source_url"] for s in profile["sources"]}
    assert urls == {"https://a.com", "https://b.com", "https://c.com/pricing"}


def test_finalize_profile_tolerates_url_string_evidence_and_tier_source() -> None:
    """Doubao's frequent mistake: filling fact.evidence / tier.source with a bare URL
    string -> passes on the first try after normalization, no more retries. Regression
    guard for the root cause behind a past timeout: 'pricing.tiers.0.source should be
    a valid dict'."""
    raw = {
        "product_name": "Z",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "定价", "category": "定价",
            "facts": [{"statement": "入门价 10 元", "evidence": ["https://a.com/price"]}],
        }],
        "pricing": {
            "pricing_model": "per_user",
            "tiers": [{"name": "Pro", "price_per_user_monthly": 10.0,
                       "source": "https://a.com/price"}],
        },
        "sources": [],
    }
    profile = _finalize("Z", json.dumps(raw)).artifact["profile"]
    assert profile["dimensions"][0]["facts"][0]["evidence"][0]["source_url"] == "https://a.com/price"
    assert profile["pricing"]["tiers"][0]["source"]["source_url"] == "https://a.com/price"


def test_finalize_profile_autofill_dedupes_against_existing_sources() -> None:
    """When the LLM has already filled in some sources, autofill doesn't add duplicates."""

    raw = {
        "product_name": "Z",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "AI", "category": "功能",
            "facts": [{"statement": "F", "evidence": [
                {"source_url": "https://a.com", "snippet": "x"},
                {"source_url": "https://b.com", "snippet": "y"},
            ]}],
        }],
        "sources": [{"source_url": "https://a.com", "snippet": "已存在"}],
    }
    profile = _finalize("Z", json.dumps(raw)).artifact["profile"]
    urls = [s["source_url"] for s in profile["sources"]]
    assert urls.count("https://a.com") == 1  # not duplicated
    assert "https://b.com" in urls           # the new URL is added
