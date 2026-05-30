"""测试 Collector exploration_node + collect_node / collect_one_product —— mock ReAct，不调真 LLM。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, ToolMessage

from cca.schema import CollectTask, CollectorExplorationResult, ProductProfile
from cca.state import CCAState


def _empty_state(**overrides) -> CCAState:
    state: CCAState = {
        "user_query": "帮我分析飞书的主要竞品",
        "target_product": "飞书",
        "user_files": None,
        "initial_brief": {
            "target_product": "飞书",
            "company_hint": "字节跳动",
            "user_query": "帮我分析飞书的主要竞品",
        },
        "domain_seed": None,
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "report_task": None,
        "profiles": {},
        "review_state": [],
        "qa_results": [],
        "report_status": "pending",
        "report_md": None,
        "report_pdf_path": None,
        "qa_notes": [],
        "audit_log": [],
        "debate_results": [],
        "agent_signals": [],
        "consumed_signal_ids": [],
        "decision_log": [],
    }
    state.update(overrides)  # type: ignore[typeddict-unknown-key]
    return state


# ── _last_tool_json(finalize_exploration) ─────────────────────────────


def test_extract_exploration_returns_dict() -> None:
    from cca.agents.collector import _last_tool_json

    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信"],
        discovered_dimensions=["视频会议", "定价"],
        initial_profiles=[],
    )
    messages = [
        AIMessage(content="思考过程..."),
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="call_1",
            name="finalize_exploration",
        ),
    ]
    result = _last_tool_json(messages, "finalize_exploration")
    assert result is not None
    assert result["target_product"] == "飞书"
    assert result["competitor_names"] == ["钉钉", "企业微信"]


def test_extract_exploration_returns_none_if_finalize_not_called() -> None:
    from cca.agents.collector import _last_tool_json

    messages = [AIMessage(content="思考但没调工具")]
    assert _last_tool_json(messages, "finalize_exploration") is None


def test_extract_exploration_takes_latest_when_called_twice() -> None:
    """LLM 偶尔会多次 finalize，应以最新一次为准。"""
    from cca.agents.collector import _last_tool_json

    early = json.dumps({
        "target_product": "X",
        "product_type": "T",
        "competitor_names": ["A"],
        "discovered_dimensions": ["d"],
        "initial_profiles": [],
    })
    late = json.dumps({
        "target_product": "Y",
        "product_type": "T",
        "competitor_names": ["B"],
        "discovered_dimensions": ["d"],
        "initial_profiles": [],
    })
    messages = [
        ToolMessage(content=early, tool_call_id="1", name="finalize_exploration"),
        ToolMessage(content=late, tool_call_id="2", name="finalize_exploration"),
    ]
    result = _last_tool_json(messages, "finalize_exploration")
    assert result is not None
    assert result["target_product"] == "Y"


# ── _extract_tool_jsons(challenge_pm) ─────────────────────────────────


def test_extract_signals_collects_challenge_pm_outputs() -> None:
    from cca.agents.collector import _extract_tool_jsons

    sig_json = json.dumps({
        "signal_id": "abc",
        "from_agent": "collector",
        "kind": "pm_challenge",
        "target": "initial_brief",
        "payload": {"claim": "X 已停服", "evidence": ["官网 404"]},
        "requires_debate": False,
        "ts": "2026-05-25T10:00:00Z",
    })
    messages = [
        ToolMessage(content=sig_json, tool_call_id="1", name="challenge_pm"),
        ToolMessage(content='[{"title": "foo"}]', tool_call_id="2", name="web_search"),
    ]
    signals = _extract_tool_jsons(messages, "challenge_pm")
    assert len(signals) == 1
    assert signals[0]["from_agent"] == "collector"


def test_extract_signals_empty_when_no_challenge() -> None:
    from cca.agents.collector import _extract_tool_jsons

    messages = [
        ToolMessage(content='[]', tool_call_id="1", name="web_search"),
    ]
    assert _extract_tool_jsons(messages, "challenge_pm") == []


# ── exploration_node ──────────────────────────────────────────────────


def _make_mock_agent(messages: list) -> MagicMock:
    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {"messages": messages}
    return mock_agent


def test_exploration_node_success_returns_required_state_fields() -> None:
    """正常路径：finalize_exploration 被调用 → 节点返回 exploration_result / competitor_names。"""
    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信"],
        discovered_dimensions=["视频会议"],
        initial_profiles=[],
    )
    mock_messages = [
        AIMessage(content="..."),
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="x",
            name="finalize_exploration",
        ),
    ]
    with patch(
        "cca.agents.collector.create_react_agent",
        return_value=_make_mock_agent(mock_messages),
    ):
        from cca.agents.collector import exploration_node
        result = exploration_node(_empty_state())

    assert result["exploration_result"]["target_product"] == "飞书"
    assert result["competitor_names"] == ["钉钉", "企业微信"]
    assert result["audit_log"][0]["event"] == "exploration_done"
    assert result["audit_log"][0]["competitor_count"] == 2


def test_exploration_node_failure_when_finalize_not_called() -> None:
    """ReAct 没调 finalize → 节点写 exploration_failed audit，不写 exploration_result。"""
    mock_messages = [AIMessage(content="I think the answer is...")]
    with patch(
        "cca.agents.collector.create_react_agent",
        return_value=_make_mock_agent(mock_messages),
    ):
        from cca.agents.collector import exploration_node
        result = exploration_node(_empty_state())

    assert "exploration_result" not in result
    assert result["audit_log"][0]["event"] == "exploration_failed"


def test_exploration_node_collects_signals_alongside_exploration() -> None:
    """同次 ReAct 既能产出 exploration 又能挑战 PM → 两者都进 state。"""
    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉"],
        discovered_dimensions=["视频会议"],
        initial_profiles=[],
    )
    sig_json = json.dumps({
        "signal_id": "abc",
        "from_agent": "collector",
        "kind": "pm_challenge",
        "target": "initial_brief",
        "payload": {"claim": "company_hint 错了", "evidence": ["官网域名 .com 不是 .cn"]},
        "requires_debate": False,
        "ts": "2026-05-25T10:00:00Z",
    })
    mock_messages = [
        ToolMessage(content=sig_json, tool_call_id="1", name="challenge_pm"),
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="2",
            name="finalize_exploration",
        ),
    ]
    with patch(
        "cca.agents.collector.create_react_agent",
        return_value=_make_mock_agent(mock_messages),
    ):
        from cca.agents.collector import exploration_node
        result = exploration_node(_empty_state())

    assert result["exploration_result"]["target_product"] == "飞书"
    assert len(result["agent_signals"]) == 1
    assert result["agent_signals"][0]["from_agent"] == "collector"
    assert result["audit_log"][0]["signals_raised"] == 1


def test_exploration_node_injects_domain_seed_hint_into_prompt() -> None:
    """state.domain_seed 存在时，prompt 应含其 dimension_candidates / competitor_mentions。"""
    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉"],
        discovered_dimensions=["视频会议"],
        initial_profiles=[],
    )
    mock_agent = _make_mock_agent([
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="x",
            name="finalize_exploration",
        ),
    ])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import exploration_node
        state = _empty_state(
            domain_seed={
                "source_files": ["uploads/m.pdf"],
                "dimension_candidates": ["视频会议", "AI 助手"],
                "competitor_mentions": ["钉钉", "企业微信"],
                "product_type_hint": "协同办公平台",
                "terminology": {},
                "extracted_at": "2026-05-25T10:00:00Z",
            },
        )
        exploration_node(state)

    # 校验 ReAct agent 收到的 prompt 含 domain_seed 内容
    call_args = mock_agent.invoke.call_args[0][0]
    human_msg = call_args["messages"][1]
    assert "PM 从用户文档蒸馏" in human_msg.content
    assert "视频会议" in human_msg.content
    assert "企业微信" in human_msg.content


def test_exploration_node_omits_seed_hint_when_no_domain_seed() -> None:
    """state.domain_seed 为 None 时 prompt 不出现 hint 段，回到纯联网路径。"""
    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉"],
        discovered_dimensions=["视频会议"],
        initial_profiles=[],
    )
    mock_agent = _make_mock_agent([
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="x",
            name="finalize_exploration",
        ),
    ])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import exploration_node
        exploration_node(_empty_state(domain_seed=None))

    call_args = mock_agent.invoke.call_args[0][0]
    human_msg = call_args["messages"][1]
    assert "PM 从用户文档蒸馏" not in human_msg.content


def test_exploration_node_uses_target_product_from_brief() -> None:
    """initial_brief.target_product 优先于 state.target_product（PM 阶段一可能更新）。"""
    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["X"],
        discovered_dimensions=["d"],
        initial_profiles=[],
    )
    mock_agent = _make_mock_agent([
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="x",
            name="finalize_exploration",
        ),
    ])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import exploration_node
        state = _empty_state(
            target_product="旧值",
            initial_brief={"target_product": "飞书", "company_hint": None, "user_query": "x"},
        )
        exploration_node(state)

    # 检查初始消息里用的是 brief 的 target_product
    call_args = mock_agent.invoke.call_args[0][0]
    human_msg = call_args["messages"][1]
    assert "飞书" in human_msg.content


# ── Phase 2: collect_one_product ─────────────────────────────────────


def _valid_profile_payload(product_name: str = "钉钉") -> dict:
    """构造一个最小可通过 ProductProfile 校验的 dict（带 evidence min_length=1）。"""
    return {
        "product_name": product_name,
        "company": "阿里巴巴",
        "product_type": "企业协作平台",
        "target_users": "中大型企业团队",
        "website": "https://www.dingtalk.com",
        "dimensions": [],
        "pricing": None,
        "sources": [],
    }


def _finalize_profile_tool_msg(product_name: str = "钉钉") -> ToolMessage:
    return ToolMessage(
        content=json.dumps({
            "product_name": product_name,
            "profile": _valid_profile_payload(product_name),
        }, ensure_ascii=False),
        tool_call_id="x",
        name="finalize_profile",
    )


def _replacement_tool_msg(product_name: str = "幽灵产品") -> ToolMessage:
    return ToolMessage(
        content=json.dumps({
            "signal_id": "abc",
            "from_agent": "collector",
            "kind": "data_gap",
            "target": "task_plan",
            "payload": {
                "claim": f"产品『{product_name}』数据无法采集：官网 404",
                "evidence": ["https://example.com/g 404", "App Store 0 命中"],
                "suggested_fix": f"从竞品列表移除 {product_name}",
            },
            "requires_debate": False,
            "ts": "2026-05-25T10:00:00Z",
        }, ensure_ascii=False),
        tool_call_id="y",
        name="request_product_replacement",
    )


def test_extract_finalized_profile_takes_latest() -> None:
    from cca.agents.collector import _extract_finalized_profile

    early = _finalize_profile_tool_msg("旧产品")
    late = _finalize_profile_tool_msg("新产品")
    messages = [early, AIMessage(content="再想想"), late]
    profile = _extract_finalized_profile(messages)
    assert profile is not None
    assert profile["product_name"] == "新产品"


def test_extract_finalized_profile_returns_none_when_not_called() -> None:
    from cca.agents.collector import _extract_finalized_profile

    assert _extract_finalized_profile([AIMessage(content="思考")]) is None


def test_extract_replacement_signals_collects_all() -> None:
    from cca.agents.collector import _extract_tool_jsons

    messages = [
        _replacement_tool_msg("X"),
        ToolMessage(content='[]', tool_call_id="z", name="web_search"),
    ]
    signals = _extract_tool_jsons(messages, "request_product_replacement")
    assert len(signals) == 1
    assert signals[0]["target"] == "task_plan"


def test_collect_one_product_success_path() -> None:
    """ReAct 调了 finalize_profile → 节点返回 profiles + audit collect_done。"""
    task = CollectTask(product_name="钉钉", priority_dimensions=["视频会议"])
    mock_agent = _make_mock_agent([
        AIMessage(content="搜了官网"),
        _finalize_profile_tool_msg("钉钉"),
    ])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import collect_one_product
        result = collect_one_product(task, context={"target_product": "飞书"})

    assert "profiles" in result
    assert "钉钉" in result["profiles"]
    assert result["profiles"]["钉钉"]["product_type"] == "企业协作平台"
    assert result["audit_log"][0]["event"] == "collect_done"
    assert result["audit_log"][0]["product_name"] == "钉钉"


def test_collect_one_product_replacement_path() -> None:
    """ReAct 调了 request_product_replacement → 节点返回 agent_signals + audit replacement_requested。"""
    task = CollectTask(product_name="幽灵产品", priority_dimensions=[])
    mock_agent = _make_mock_agent([_replacement_tool_msg("幽灵产品")])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import collect_one_product
        result = collect_one_product(task, context={"target_product": "飞书"})

    assert "profiles" not in result
    assert len(result["agent_signals"]) == 1
    assert result["agent_signals"][0]["from_agent"] == "collector"
    assert result["audit_log"][0]["event"] == "collect_replacement_requested"


def test_collect_one_product_failed_path() -> None:
    """ReAct 既没 finalize 也没 request_replacement → 节点 audit collect_failed。"""
    task = CollectTask(product_name="钉钉", priority_dimensions=[])
    mock_agent = _make_mock_agent([AIMessage(content="我想了想就放弃了")])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import collect_one_product
        result = collect_one_product(task, context={"target_product": "飞书"})

    assert "profiles" not in result
    assert "agent_signals" not in result
    assert result["audit_log"][0]["event"] == "collect_failed"


def test_collect_one_product_passes_domain_seed_hint_to_prompt() -> None:
    task = CollectTask(product_name="钉钉", priority_dimensions=["视频会议"])
    mock_agent = _make_mock_agent([_finalize_profile_tool_msg("钉钉")])
    with patch("cca.agents.collector.create_react_agent", return_value=mock_agent):
        from cca.agents.collector import collect_one_product
        collect_one_product(task, context={
            "target_product": "飞书",
            "domain_seed": {
                "product_type_hint": "企业协作平台",
                "terminology": {"DAU": "日活跃用户"},
            },
        })

    call_args = mock_agent.invoke.call_args[0][0]
    human_msg = call_args["messages"][1]
    assert "domain_seed_hint" in human_msg.content
    assert "企业协作平台" in human_msg.content


def testbuild_collect_context_finds_product_brief() -> None:
    """build_collect_context 从 exploration_result.initial_profiles 找该产品的 brief。"""
    from cca.agents.collector import build_collect_context

    state = _empty_state(
        exploration_result={
            "target_product": "飞书",
            "product_type": "协作平台",
            "competitor_names": ["钉钉"],
            "discovered_dimensions": [],
            "initial_profiles": [
                {"product_name": "钉钉", "company": "阿里", "website": "https://dingtalk.com"},
            ],
        },
    )
    ctx = build_collect_context(state, "钉钉")
    assert ctx["target_product"] == "飞书"
    assert ctx["product_brief"]["company"] == "阿里"


def testbuild_collect_context_no_match_returns_none_brief() -> None:
    from cca.agents.collector import build_collect_context

    state = _empty_state(exploration_result={"initial_profiles": []})
    ctx = build_collect_context(state, "未知产品")
    assert ctx["product_brief"] is None


# ── cache key 稳定切片（回归防线）─────────────────────────────────────


def test_stable_domain_seed_strips_extracted_at() -> None:
    """extracted_at 浮动不该影响 cache key —— 这是 P0 修复的核心不变量。"""
    from cca.agents.collector import _stable_domain_seed

    seed_a = {
        "product_type_hint": "协作", "terminology": {"DAU": "日活"},
        "extracted_at": "2026-05-25T10:00:00Z",
    }
    seed_b = {**seed_a, "extracted_at": "2026-05-26T11:23:45Z"}
    assert _stable_domain_seed(seed_a) == _stable_domain_seed(seed_b)
    assert "extracted_at" not in _stable_domain_seed(seed_a)
    assert _stable_domain_seed(None) is None
    assert _stable_domain_seed({}) == {}


def test_stable_product_brief_keeps_only_prompt_fields() -> None:
    """未来扩 ProductBrief 加新字段时不应污染 cache —— P1 修复的契约。"""
    from cca.agents.collector import _stable_product_brief

    brief = {
        "product_name": "钉钉", "company": "阿里", "website": "https://d.com",
        "product_type": "协作", "future_field": "should_be_dropped",
    }
    out = _stable_product_brief(brief)
    assert set(out.keys()) == {"product_name", "company", "website", "product_type"}
    assert "future_field" not in out
    assert _stable_product_brief(None) is None


def test_cache_key_hash_stable_under_floating_fields() -> None:
    """端到端不变量：domain_seed.extracted_at + ProductBrief 未知扩展字段
    不影响最终 react_cache hash。这条断言挂掉 = 答辩现场 replay miss 风险回归。"""
    from cca.agents.collector import _stable_domain_seed, _stable_product_brief
    from cca.memory.react_cache import hash_key

    base_key = {
        "task": {"product_name": "钉钉", "priority_dimensions": [], "allow_self_extension": True},
        "target_product": "飞书",
        "domain_seed": _stable_domain_seed({
            "product_type_hint": "协作", "terminology": {},
            "extracted_at": "2026-05-25T10:00:00Z",
        }),
        "product_brief": _stable_product_brief({
            "product_name": "钉钉", "company": "阿里", "website": "https://d.com",
            "product_type": "协作",
        }),
    }
    drifted_key = {
        **base_key,
        "domain_seed": _stable_domain_seed({
            "product_type_hint": "协作", "terminology": {},
            "extracted_at": "2026-99-99T99:99:99Z",   # 时间戳浮动
        }),
        "product_brief": _stable_product_brief({
            "product_name": "钉钉", "company": "阿里", "website": "https://d.com",
            "product_type": "协作", "discovered_at": "later",  # 未来字段
        }),
    }
    assert hash_key(base_key) == hash_key(drifted_key)
