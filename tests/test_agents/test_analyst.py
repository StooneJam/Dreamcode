"""Analyst Agent 测试。

覆盖：
- finalize_swot 工具：schema 验证与输出结构
- submit_dimension_ranking 工具：排名条目验证
- challenge_pm 工具：AgentSignal 结构与字段
- analyst_node：跳过 guard / SWOT 写入 profiles / audit_log 格式 / 无信号默认
- _slim_profile：裁剪辅助函数行为
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cca.schema import SWOT, SWOTPoint


# ─── Helpers ───────────────────────────────────────────────────────────────

def _make_swot(name: str) -> SWOT:
    point = SWOTPoint(
        point=f"{name} 优势",
        supporting_fact_statements=[f"{name} Pro 版按用户每月 30 元"],
    )
    return SWOT(strengths=[point], weaknesses=[point], opportunities=[point], threats=[point])


def _tool_message(tool_name: str, content: str):
    from langchain_core.messages import ToolMessage
    return ToolMessage(content=content, name=tool_name, tool_call_id="fake-id")


def _swot_msg(product_name: str):
    payload = json.dumps({
        "product_name": product_name,
        "swot": _make_swot(product_name).model_dump(),
    })
    return _tool_message("finalize_swot", payload)


def _ranking_msg(dimension: str, products: list[str]):
    payload = json.dumps({
        "dimension": dimension,
        "ranking": [
            {"product_name": p, "rank": i + 1, "note": f"{p} 在此维度第 {i + 1}"}
            for i, p in enumerate(products)
        ],
    })
    return _tool_message("submit_dimension_ranking", payload)


# ─── finalize_swot ─────────────────────────────────────────────────────────

class TestFinalizeSwotTool:
    def test_returns_product_name_and_swot(self):
        from cca.tools.analyst_tools import finalize_swot
        result = json.loads(finalize_swot.invoke({
            "product_name": "钉钉",
            "swot_json": _make_swot("钉钉").model_dump_json(),
        }))
        assert result["product_name"] == "钉钉"
        assert "strengths" in result["swot"]

    def test_all_four_quadrants_present(self):
        from cca.tools.analyst_tools import finalize_swot
        result = json.loads(finalize_swot.invoke({
            "product_name": "飞书",
            "swot_json": _make_swot("飞书").model_dump_json(),
        }))
        for quadrant in ("strengths", "weaknesses", "opportunities", "threats"):
            assert quadrant in result["swot"]

    def test_invalid_swot_raises(self):
        from cca.tools.analyst_tools import finalize_swot
        with pytest.raises(Exception):
            finalize_swot.invoke({"product_name": "X", "swot_json": '{"bad": true}'})

    def test_supporting_facts_preserved(self):
        from cca.tools.analyst_tools import finalize_swot
        result = json.loads(finalize_swot.invoke({
            "product_name": "企业微信",
            "swot_json": _make_swot("企业微信").model_dump_json(),
        }))
        first_strength = result["swot"]["strengths"][0]
        assert len(first_strength["supporting_fact_statements"]) >= 1


# ─── submit_dimension_ranking ───────────────────────────────────────────────

class TestSubmitDimensionRankingTool:
    def _rankings_json(self) -> str:
        return json.dumps([
            {"product_name": "飞书", "rank": 1, "note": "最大支持 500 人"},
            {"product_name": "钉钉", "rank": 2, "note": "最大支持 300 人"},
        ])

    def test_returns_dimension_and_ranking(self):
        from cca.tools.analyst_tools import submit_dimension_ranking
        result = json.loads(submit_dimension_ranking.invoke({
            "dimension_name": "视频会议人数上限",
            "rankings_json": self._rankings_json(),
        }))
        assert result["dimension"] == "视频会议人数上限"
        assert len(result["ranking"]) == 2

    def test_rank_values_preserved(self):
        from cca.tools.analyst_tools import submit_dimension_ranking
        result = json.loads(submit_dimension_ranking.invoke({
            "dimension_name": "定价",
            "rankings_json": self._rankings_json(),
        }))
        ranks = [e["rank"] for e in result["ranking"]]
        assert 1 in ranks and 2 in ranks

    def test_note_preserved(self):
        from cca.tools.analyst_tools import submit_dimension_ranking
        result = json.loads(submit_dimension_ranking.invoke({
            "dimension_name": "定价",
            "rankings_json": self._rankings_json(),
        }))
        notes = [e["note"] for e in result["ranking"]]
        assert any("500" in n for n in notes)

    def test_invalid_entry_missing_rank_raises(self):
        from cca.tools.analyst_tools import submit_dimension_ranking
        bad = json.dumps([{"product_name": "飞书", "note": "好"}])
        with pytest.raises(Exception):
            submit_dimension_ranking.invoke({"dimension_name": "定价", "rankings_json": bad})


# ─── challenge_pm ──────────────────────────────────────────────────────────

class TestChallengePmTool:
    def test_returns_valid_agent_signal(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        result = challenge_pm.invoke({
            "claim": "product_names 中 Zoom 在 profiles 中完全缺失",
            "evidence": ["profiles dict 中不存在 key 'Zoom'"],
        })
        signal = AgentSignal.model_validate_json(result)
        assert signal.from_agent == "analyst"
        # requires_debate 默认 False（事实性信号）→ kind 应为 data_gap
        assert signal.kind == "data_gap"
        assert signal.target == "analyst_task"

    def test_requires_debate_propagated(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        result = challenge_pm.invoke({
            "claim": "focus_dimensions 不适合 SaaS 产品",
            "evidence": ["维度均为硬件规格类"],
            "requires_debate": True,
        })
        assert AgentSignal.model_validate_json(result).requires_debate is True

    def test_signal_id_unique_per_call(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        r1 = challenge_pm.invoke({"claim": "c1", "evidence": ["e1"]})
        r2 = challenge_pm.invoke({"claim": "c2", "evidence": ["e2"]})
        assert AgentSignal.model_validate_json(r1).signal_id != AgentSignal.model_validate_json(r2).signal_id

    def test_factual_signal_uses_data_gap_kind(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        result = challenge_pm.invoke({
            "claim": "product X 在 profiles 中完全缺失",
            "evidence": ["profiles dict 无 key 'X'"],
            "requires_debate": False,
        })
        assert AgentSignal.model_validate_json(result).kind == "data_gap"

    def test_subjective_signal_uses_pm_challenge_kind(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        result = challenge_pm.invoke({
            "claim": "focus_dimensions 不适合该产品领域",
            "evidence": ["维度均为硬件规格"],
            "requires_debate": True,
        })
        assert AgentSignal.model_validate_json(result).kind == "pm_challenge"

    def test_payload_claim_matches(self):
        from cca.schema import AgentSignal
        from cca.tools.analyst_tools import challenge_pm
        claim_text = "某产品 dimensions 为空，无法支撑 SWOT"
        result = challenge_pm.invoke({"claim": claim_text, "evidence": ["dimensions: []"]})
        assert AgentSignal.model_validate_json(result).payload.claim == claim_text


# ─── analyst_node ──────────────────────────────────────────────────────────

class TestAnalystNode:
    def _invoke(self, mock_state, extra_msgs=None):
        msgs = [
            _swot_msg("钉钉"),
            _swot_msg("企业微信"),
            _ranking_msg("视频会议人数上限", ["钉钉", "企业微信"]),
        ] + (extra_msgs or [])
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": msgs}
        with patch("cca.agents.analyst.create_react_agent", return_value=mock_agent):
            from cca.agents.analyst import analyst_node
            return analyst_node(mock_state)

    def test_returns_required_keys(self, mock_state):
        result = self._invoke(mock_state)
        for key in ("profiles", "agent_signals", "audit_log"):
            assert key in result

    def test_swot_written_to_profiles(self, mock_state):
        result = self._invoke(mock_state)
        assert result["profiles"]["钉钉"]["swot"] is not None
        assert result["profiles"]["企业微信"]["swot"] is not None

    def test_swot_has_four_quadrants(self, mock_state):
        result = self._invoke(mock_state)
        swot = result["profiles"]["钉钉"]["swot"]
        for key in ("strengths", "weaknesses", "opportunities", "threats"):
            assert key in swot

    def test_ranking_in_audit_log(self, mock_state):
        result = self._invoke(mock_state)
        events = [e.get("event") for e in result["audit_log"]]
        assert "dimension_ranked" in events

    def test_summary_audit_log_present(self, mock_state):
        result = self._invoke(mock_state)
        events = [e.get("event") for e in result["audit_log"]]
        assert "analysis_done" in events

    def test_summary_lists_swot_products(self, mock_state):
        result = self._invoke(mock_state)
        summary = next(e for e in result["audit_log"] if e.get("event") == "analysis_done")
        assert "钉钉" in summary["swot_products"]
        assert "企业微信" in summary["swot_products"]

    def test_no_signals_by_default(self, mock_state):
        result = self._invoke(mock_state)
        assert result["agent_signals"] == []

    def test_challenge_signal_propagated(self, mock_state):
        from cca.tools.analyst_tools import challenge_pm
        signal_json = challenge_pm.invoke({
            "claim": "focus_dimensions 维度不合理",
            "evidence": ["SaaS 产品不需要 GPU 规格维度"],
            "requires_debate": True,
        })
        challenge_msg = _tool_message("challenge_pm", signal_json)
        result = self._invoke(mock_state, extra_msgs=[challenge_msg])
        assert len(result["agent_signals"]) == 1
        assert result["agent_signals"][0]["from_agent"] == "analyst"

    def test_skips_when_analyst_task_none(self, mock_state):
        from cca.agents.analyst import analyst_node
        state = {**mock_state, "analyst_task": None}
        result = analyst_node(state)
        assert result["audit_log"][0]["event"] == "skipped"

    def test_require_swot_false_suppresses_finalize_swot(self, mock_state):
        """require_swot=False 时 human message 提示不调 finalize_swot，且无 SWOT 产出。"""
        from cca.schema import AnalystTask
        state = {
            **mock_state,
            "analyst_task": AnalystTask(
                product_names=["钉钉"],
                focus_dimensions=["定价"],
                require_swot=False,
            ).model_dump(),
        }
        # 模拟 agent 没有调 finalize_swot（遵从指令）
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [
            _ranking_msg("定价", ["钉钉"]),
        ]}
        with patch("cca.agents.analyst.create_react_agent", return_value=mock_agent):
            from cca.agents.analyst import analyst_node
            result = analyst_node(state)
        assert result["profiles"] == {}

    def test_target_product_in_human_message(self, mock_state):
        """target_product 必须出现在传给 LLM 的 human message 中。"""
        from cca.schema import AnalystTask
        from cca.agents.analyst import _build_human_message
        task = AnalystTask(product_names=["飞书", "钉钉"], focus_dimensions=["定价"])
        msg = _build_human_message(task, {}, "飞书")
        assert "飞书" in msg
        assert "target_product" in msg

    def test_collector_fields_preserved_via_reducer(self, mock_state):
        """analyst_node 只写 swot 增量；_merge_profiles reducer 保留 Collector 字段。"""
        from cca.state import _merge_profiles
        result = self._invoke(mock_state)
        merged = _merge_profiles(mock_state["profiles"], result["profiles"])
        assert "dimensions" in merged["钉钉"]
        assert "swot" in merged["钉钉"]


# ─── _slim_profile ─────────────────────────────────────────────────────────

class TestSlimProfile:
    def test_keeps_dimension_statements(self):
        from cca.agents.analyst import _slim_profile
        profile = {
            "dimensions": [{"name": "价格", "category": "定价",
                             "facts": [{"statement": "Pro 30元", "evidence": [{"source_url": "http://x.com"}]}],
                             "cross_product_note": "低于均值"}],
            "pricing": None,
            "sentiment": None,
        }
        slim = _slim_profile(profile)
        assert slim["dimensions"][0]["facts"][0]["statement"] == "Pro 30元"

    def test_removes_evidence_urls(self):
        from cca.agents.analyst import _slim_profile
        profile = {
            "dimensions": [{"name": "价格", "category": "定价",
                             "facts": [{"statement": "30元", "evidence": [{"source_url": "http://x.com"}]}],
                             "cross_product_note": None}],
            "pricing": None,
            "sentiment": None,
        }
        slim = _slim_profile(profile)
        # evidence key 应被去掉
        assert "evidence" not in slim["dimensions"][0]["facts"][0]

    def test_sentiment_trimmed_to_themes_and_rating(self):
        from cca.agents.analyst import _slim_profile
        profile = {
            "dimensions": [],
            "pricing": None,
            "sentiment": {
                "appstore_cn_rating": 4.2,
                "appstore_cn_review_count": 5000,
                "positive_themes": ["好用"],
                "negative_themes": ["卡顿"],
                "representative_reviews": ["很长的评论文本" * 20],
            },
        }
        slim = _slim_profile(profile)
        assert slim["sentiment"]["appstore_cn_rating"] == 4.2
        assert slim["sentiment"]["positive_themes"] == ["好用"]
        # representative_reviews 被裁掉
        assert "representative_reviews" not in slim["sentiment"]
