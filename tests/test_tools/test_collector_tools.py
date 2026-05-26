"""测试 collector_tools：finalize_exploration 校验 schema，challenge_pm 构造 AgentSignal。"""
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


def test_finalize_exploration_rejects_missing_required_field() -> None:
    """缺 competitor_names 等 required 字段 → Pydantic ValidationError。"""
    from cca.tools.collector_tools import finalize_exploration

    invalid = json.dumps({"target_product": "飞书"})  # 缺 product_type / competitor_names / ...
    with pytest.raises(ValidationError):
        finalize_exploration.invoke({"result_json": invalid})


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
    """ChallengePayload 强制 evidence min_length=1，零证据挑战被拒。"""
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


# ── Phase 2 工具 ───────────────────────────────────────────────────────


def _valid_profile_json(product_name: str = "钉钉") -> str:
    """构造一个最小可通过 ProductProfile 校验的 JSON。"""
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


def test_finalize_profile_accepts_valid_schema() -> None:
    from cca.tools.collector_tools import finalize_profile

    output = finalize_profile.invoke({
        "product_name": "钉钉",
        "profile_json": _valid_profile_json("钉钉"),
    })
    parsed = json.loads(output)
    assert parsed["product_name"] == "钉钉"
    assert parsed["profile"]["company"] == "阿里巴巴"
    assert parsed["profile"]["website"] == "https://www.dingtalk.com"


def test_finalize_profile_overrides_mismatched_product_name() -> None:
    """profile_json 里的 product_name 跟参数不一致 → 以参数为准（防 LLM 拼错）。"""
    from cca.tools.collector_tools import finalize_profile

    output = finalize_profile.invoke({
        "product_name": "钉钉",
        "profile_json": _valid_profile_json("DingTalk"),  # 不一致
    })
    parsed = json.loads(output)
    assert parsed["product_name"] == "钉钉"
    assert parsed["profile"]["product_name"] == "钉钉"


def test_finalize_profile_rejects_invalid_schema() -> None:
    from cca.tools.collector_tools import finalize_profile

    invalid = json.dumps({"product_name": "X", "product_type": 12345})  # type 错
    with pytest.raises(ValidationError):
        finalize_profile.invoke({"product_name": "X", "profile_json": invalid})


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
    """ChallengePayload 强制 evidence min_length=1；空 evidence 应被拒。"""
    from cca.tools.collector_tools import request_product_replacement

    with pytest.raises(ValidationError):
        request_product_replacement.invoke({
            "product_name": "X",
            "reason": "无理由",
            "evidence": [],
        })
