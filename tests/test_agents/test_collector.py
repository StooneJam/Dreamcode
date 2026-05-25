"""测试 Collector exploration_node —— mock ReAct agent，不调真 LLM。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, ToolMessage

from cca.schema import CollectorExplorationResult
from cca.state import CCAState


def _empty_state(**overrides) -> CCAState:
    state: CCAState = {
        "user_query": "帮我分析飞书的主要竞品",
        "target_product": "飞书",
        "initial_brief": {
            "target_product": "飞书",
            "company_hint": "字节跳动",
            "user_query": "帮我分析飞书的主要竞品",
        },
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "analyst_task": None,
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


# ── _extract_exploration ──────────────────────────────────────────────


def test_extract_exploration_returns_dict() -> None:
    from cca.agents.collector import _extract_exploration

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
    result = _extract_exploration(messages)
    assert result is not None
    assert result["target_product"] == "飞书"
    assert result["competitor_names"] == ["钉钉", "企业微信"]


def test_extract_exploration_returns_none_if_finalize_not_called() -> None:
    from cca.agents.collector import _extract_exploration

    messages = [AIMessage(content="思考但没调工具")]
    assert _extract_exploration(messages) is None


def test_extract_exploration_takes_latest_when_called_twice() -> None:
    """LLM 偶尔会多次 finalize，应以最新一次为准。"""
    from cca.agents.collector import _extract_exploration

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
    result = _extract_exploration(messages)
    assert result is not None
    assert result["target_product"] == "Y"


# ── _extract_signals ──────────────────────────────────────────────────


def test_extract_signals_collects_challenge_pm_outputs() -> None:
    from cca.agents.collector import _extract_signals

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
    signals = _extract_signals(messages)
    assert len(signals) == 1
    assert signals[0]["from_agent"] == "collector"


def test_extract_signals_empty_when_no_challenge() -> None:
    from cca.agents.collector import _extract_signals

    messages = [
        ToolMessage(content='[]', tool_call_id="1", name="web_search"),
    ]
    assert _extract_signals(messages) == []


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
