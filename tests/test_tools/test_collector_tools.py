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


def test_finalize_exploration_returns_error_on_missing_required_field() -> None:
    """缺 competitor_names 等 required 字段 → 返回 LLM-friendly 错误字符串（不 raise）。"""
    from cca.tools.collector_tools import finalize_exploration

    invalid = json.dumps({"target_product": "飞书"})  # 缺 product_type / competitor_names / ...
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


def _finalize(product_name: str, profile_json: str):
    """用 ToolCall 形式 invoke，拿到带 .artifact 的 ToolMessage（content 只给模型看停止指令）。"""
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
    """模型只看 content：必须是成功+停止指令，绝不能回显 profile JSON（防 859da7c 死循环回归）。"""
    from cca.tools.collector_tools import finalize_profile

    content = finalize_profile.invoke({  # invoke(dict) 返回 content 字符串本身
        "product_name": "钉钉", "profile_json": _valid_profile_json("钉钉"),
    })
    assert isinstance(content, str)
    assert "不得再次调用 finalize_profile" in content


def test_finalize_profile_overrides_mismatched_product_name() -> None:
    """profile_json 里的 product_name 跟参数不一致 → 以参数为准（防 LLM 拼错）。"""
    msg = _finalize("钉钉", _valid_profile_json("DingTalk"))  # 不一致
    assert msg.artifact["profile"]["product_name"] == "钉钉"


def test_finalize_profile_returns_error_string_on_invalid_schema() -> None:
    """schema 校验失败时返回错误字符串（不 raise），让 LLM 看到 ToolMessage 自修。

    create_react_agent 里抛异常会中断 ReAct loop，所以走返回值路径。
    """
    from cca.tools.collector_tools import finalize_profile

    invalid = json.dumps({"product_name": "X", "product_type": 12345})  # type 错
    result = finalize_profile.invoke({"product_name": "X", "profile_json": invalid})
    assert "ProductProfile 校验失败" in result
    assert "字段规则提示" in result


def test_finalize_profile_cleans_evidence_missing_source_url() -> None:
    """Evidence 缺 source_url 是 LLM 常见偏差；本工具应剔除而非阻断整个产品。"""
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
            {"snippet": "no url"},  # 应被剔除
        ],
    }
    profile = _finalize("Y", json.dumps(raw)).artifact["profile"]
    assert len(profile["dimensions"][0]["facts"]) == 1  # 缺 url fact 被剔
    assert len(profile["sources"]) == 1                 # 缺 url sources 项被剔


def test_finalize_profile_keeps_dimensions_when_category_missing() -> None:
    """放松后：dimension 漏 category（本次 husk 元凶）不再毁掉整段 dimensions，原样入库。"""
    raw = {
        "product_name": "W",
        "product_type": "SaaS",
        "dimensions": [{
            "name": "AI",  # 故意漏 category
            "facts": [{"statement": "F", "evidence": [{"source_url": "https://a.com"}]}],
        }],
    }
    msg = _finalize("W", json.dumps(raw))
    assert "提交成功" in msg.content
    assert len(msg.artifact["profile"]["dimensions"]) == 1     # 维度保住，不再 husk
    assert msg.artifact["profile"]["dimensions"][0]["category"] == ""


def test_finalize_profile_normalizes_fact_text_under_any_key() -> None:
    """模型把事实正文放在任意非 statement key（content/value/snippet/没见过的 key）→ 取最长字符串
    归一到 statement，保住正文不 husk。不靠别名白名单，换产品也泛化。"""
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
    assert len(facts) == 4                                  # 4 条都没被当成空 fact 丢掉
    assert all(long in f["statement"] for f in facts)       # 任意 key 的正文都被归一回 statement


def test_finalize_profile_coerces_invalid_pricing_model() -> None:
    """放松后：非法 pricing_model 归 unknown，pricing 整段保住，不再被剥。"""
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
    """ChallengePayload 强制 evidence min_length=1；空 evidence 应被拒。"""
    from cca.tools.collector_tools import request_product_replacement

    with pytest.raises(ValidationError):
        request_product_replacement.invoke({
            "product_name": "X",
            "reason": "无理由",
            "evidence": [],
        })


def test_finalize_profile_autofills_sources_from_evidence() -> None:
    """LLM 漏填顶层 sources 时，工具应从 dimensions/pricing 的 evidence 自动聚合 URL。
    R4 兜底：不依赖 LLM 自觉。"""

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
        "sources": [],  # ← LLM 漏填，工具应兜底
    }
    profile = _finalize("Z", json.dumps(raw)).artifact["profile"]
    urls = {s["source_url"] for s in profile["sources"]}
    assert urls == {"https://a.com", "https://b.com", "https://c.com/pricing"}


def test_finalize_profile_autofill_dedupes_against_existing_sources() -> None:
    """LLM 已经填了部分 sources 时，autofill 不重复添加。"""

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
    assert urls.count("https://a.com") == 1  # 不重复
    assert "https://b.com" in urls           # 新 URL 加上
