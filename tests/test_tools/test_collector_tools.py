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
