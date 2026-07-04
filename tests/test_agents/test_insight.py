"""Insight Agent tests.

Covers:
- questionnaire caching (mocked SQLite path)
- questionnaire fill_mode (real mode returns an empty list)
- questionnaire design / formatting / anonymization (mocked LLM)
- insight_one_product's output structure (mocked agent)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from cca.skills.questionnaire.anonymize import anonymize_responses
from cca.skills.questionnaire.collect import QuestionResponse, SurveyResponse
from cca.skills.questionnaire.design import Question, Questionnaire
from cca.skills.questionnaire.distribute import format_questionnaire


# ---------------------------------------------------------------------------
# Questionnaire formatting
# ---------------------------------------------------------------------------

class TestFormatQuestionnaire:
    def _make_q(self) -> Questionnaire:
        return Questionnaire(
            product_name="飞书",
            competitor_names=["钉钉", "企业微信"],
            questions=[
                Question(id="q1", text="你对飞书整体满意度？", q_type="rating_5"),
                Question(id="q2", text="最常用的功能？", q_type="multiple_choice",
                         options=["文档", "会议", "消息"]),
                Question(id="q3", text="你最希望改进哪里？", q_type="open_text"),
            ],
        )

    def test_contains_product_name(self):
        text = format_questionnaire(self._make_q())
        assert "飞书" in text

    def test_contains_all_question_ids(self):
        text = format_questionnaire(self._make_q())
        assert "q1" in text and "q2" in text and "q3" in text

    def test_contains_options(self):
        text = format_questionnaire(self._make_q())
        assert "文档" in text and "会议" in text


# ---------------------------------------------------------------------------
# Questionnaire anonymization
# ---------------------------------------------------------------------------

class TestAnonymizeResponses:
    def _make_responses(self) -> list[SurveyResponse]:
        return [
            SurveyResponse(
                respondent_id="user-12345678-abcd",
                product_name="飞书",
                answers=[
                    QuestionResponse(question_id="q1", answer="4"),
                    QuestionResponse(question_id="q3", answer="联系我 13812345678 或 test@example.com"),
                ],
            )
        ]

    def test_respondent_id_truncated(self):
        result = anonymize_responses(self._make_responses())
        assert result[0].respondent_id.startswith("anon_")
        assert "12345678-abcd" not in result[0].respondent_id

    def test_phone_scrubbed(self):
        result = anonymize_responses(self._make_responses())
        answers = {a.question_id: a.answer for a in result[0].answers}
        assert "13812345678" not in answers["q3"]
        assert "[手机号]" in answers["q3"]

    def test_email_scrubbed(self):
        result = anonymize_responses(self._make_responses())
        answers = {a.question_id: a.answer for a in result[0].answers}
        assert "test@example.com" not in answers["q3"]
        assert "[邮箱]" in answers["q3"]

    def test_rating_answer_unchanged(self):
        result = anonymize_responses(self._make_responses())
        answers = {a.question_id: a.answer for a in result[0].answers}
        assert answers["q1"] == "4"


# ---------------------------------------------------------------------------
# insight_one_product integration (mocked agent) -- the Send fanout worker, the
# real path taken by the main graph and the demo
# ---------------------------------------------------------------------------

class TestInsightOneProduct:
    def _make_tool_message(self, name: str, content: str):
        from langchain_core.messages import ToolMessage
        return ToolMessage(content=content, name=name, tool_call_id="fake-id")

    def _fake_sentiment(self, product_name: str) -> str:
        from cca.schema import UserSentiment
        s = UserSentiment(
            aggregate_rating=4.2,
            positive_themes=["界面简洁", "通知及时"],
            negative_themes=["偶发卡顿"],
        )
        return json.dumps({"product_name": product_name, "sentiment": s.model_dump()})

    def _fake_events(self, product_name: str) -> str:
        events = [{
            "statement": f"{product_name} 推出某活动，部分加盟商称亏损抵制",
            "evidence": [{"source_url": "https://news.example.com/x", "snippet": "原文片段"}],
        }]
        return json.dumps({"product_name": product_name, "key_events": events})

    def _invoke(self, mock_state, product_name="钉钉", extra_msgs=None):
        from cca.schema import InsightTask
        msgs = [self._make_tool_message("finalize_sentiment", self._fake_sentiment(product_name))]
        if extra_msgs:
            msgs.extend(extra_msgs)
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": msgs}
        context = {
            "profiles": mock_state["profiles"],
            "competitor_names": mock_state["competitor_names"],
            "target_product": mock_state["target_product"],
        }
        with patch("cca.agents.insight.create_react_agent", return_value=mock_agent):
            from cca.agents.insight import insight_one_product
            return insight_one_product(InsightTask(product_name=product_name), context)

    def test_sentiment_written_to_profiles(self, mock_state):
        result = self._invoke(mock_state)
        assert result["profiles"]["钉钉"]["sentiment"] is not None

    def test_collector_data_preserved(self, mock_state):
        # insight_one_product only returns the delta {"sentiment": ...}; the
        # _merge_profiles reducer preserves Collector's fields.
        # This simulates LangGraph's reducer-merge behavior, verifying dimensions
        # survive the merge.
        from cca.state import _merge_profiles
        result = self._invoke(mock_state)
        merged = _merge_profiles(mock_state["profiles"], result["profiles"])
        assert "dimensions" in merged["钉钉"]
        assert "sentiment" in merged["钉钉"]

    def test_audit_log_records_product(self, mock_state):
        result = self._invoke(mock_state)
        log = result["audit_log"][0]
        assert log["agent"] == "insight"
        assert log["product"] == "钉钉"
        assert log["sentiment_written"] is True

    def test_no_signals_by_default(self, mock_state):
        # a fanout worker with no signal omits the agent_signals key (a minimal delta contract)
        result = self._invoke(mock_state)
        assert "agent_signals" not in result

    def test_key_events_written_to_profiles(self, mock_state):
        msg = self._make_tool_message("record_key_events", self._fake_events("钉钉"))
        result = self._invoke(mock_state, extra_msgs=[msg])
        events = result["profiles"]["钉钉"]["key_events"]
        assert len(events) == 1 and "抵制" in events[0]["statement"]
        assert result["audit_log"][0]["key_events_written"] is True

    def test_key_events_absent_when_not_recorded(self, mock_state):
        # when record_key_events isn't called, key_events isn't written, but sentiment still is
        result = self._invoke(mock_state)
        assert "key_events" not in result["profiles"]["钉钉"]
        assert result["audit_log"][0]["key_events_written"] is False


# ---------------------------------------------------------------------------
# _build_insight_product_message: product_type -> data-source channel injection
# ---------------------------------------------------------------------------

class TestInsightProductMessage:
    def _build(self, product_type: str):
        from cca.agents.insight import _build_insight_product_message
        from cca.schema import InsightTask
        return _build_insight_product_message(
            InsightTask(product_name="幸运咖"), {}, ["星巴克", "瑞幸", "Manner"], product_type,
        )

    def test_coffee_routes_to_local_life_channel(self):
        msg = self._build("连锁咖啡")
        assert "大众点评" in msg and "美团" in msg

    def test_coffee_message_excludes_app_store(self):
        # "Lucky Coffee" has an app, but the category is coffee -> the message must not steer it toward scraping App Store
        msg = self._build("连锁咖啡")
        assert "scrape_app_store" not in msg

    def test_coffee_message_uses_scrape_local_life(self):
        # structured ratings for the local-life channel go through the Google Places tool
        msg = self._build("连锁咖啡")
        assert "scrape_local_life" in msg

    def test_software_routes_to_app_store_channel(self):
        msg = self._build("协同办公软件")
        assert "scrape_app_store" in msg


# ---------------------------------------------------------------------------
# Questionnaire caching (get_or_create_questionnaire)
# ---------------------------------------------------------------------------

class TestGetOrCreateQuestionnaire:
    def _make_q(self):
        from cca.skills.questionnaire.design import Question, Questionnaire
        return Questionnaire(
            product_name="飞书",
            competitor_names=["钉钉"],
            questions=[Question(id="q1", text="满意度？", q_type="rating_5")],
        )

    def test_cache_miss_calls_design(self, tmp_path, monkeypatch):
        from unittest.mock import patch
        from cca.skills.questionnaire import collect as collect_mod
        monkeypatch.setattr(collect_mod, "_db_path", lambda: tmp_path / "test.db")
        q = self._make_q()
        with patch.object(collect_mod, "design_questionnaire", return_value=q) as mock_design:
            from cca.skills.questionnaire.collect import get_or_create_questionnaire
            result = get_or_create_questionnaire("飞书", ["钉钉"], ["协同"])
        mock_design.assert_called_once()
        assert result.product_name == "飞书"

    def test_cache_hit_skips_design(self, tmp_path, monkeypatch):
        from unittest.mock import patch
        from cca.skills.questionnaire import collect as collect_mod
        monkeypatch.setattr(collect_mod, "_db_path", lambda: tmp_path / "test.db")
        q = self._make_q()
        with patch.object(collect_mod, "design_questionnaire", return_value=q) as mock_design:
            from cca.skills.questionnaire.collect import get_or_create_questionnaire
            get_or_create_questionnaire("飞书", ["钉钉"], ["协同"])
            # second call, different competitors/dimensions but the same product name -> should hit the cache
            result = get_or_create_questionnaire("飞书", ["企业微信"], ["定价"])
        assert mock_design.call_count == 1
        assert result.product_name == "飞书"

    def test_different_products_call_design_each(self, tmp_path, monkeypatch):
        from unittest.mock import patch
        from cca.skills.questionnaire import collect as collect_mod
        monkeypatch.setattr(collect_mod, "_db_path", lambda: tmp_path / "test.db")

        from cca.skills.questionnaire.design import Question, Questionnaire
        def make_q(product_name, *args, **kwargs):
            return Questionnaire(
                product_name=product_name,
                competitor_names=[],
                questions=[Question(id="q1", text="?", q_type="rating_5")],
            )

        with patch.object(collect_mod, "design_questionnaire", side_effect=make_q) as mock_design:
            from cca.skills.questionnaire.collect import get_or_create_questionnaire
            get_or_create_questionnaire("飞书", [], [])
            get_or_create_questionnaire("钉钉", [], [])
        assert mock_design.call_count == 2


# ---------------------------------------------------------------------------
# Questionnaire fill_mode
# ---------------------------------------------------------------------------

class TestCollectResponsesFillMode:
    def _make_q(self):
        from cca.skills.questionnaire.design import Question, Questionnaire
        return Questionnaire(
            product_name="测试产品",
            competitor_names=[],
            questions=[Question(id="q1", text="满意度？", q_type="rating_5")],
        )

    def test_real_mode_returns_empty(self):
        from cca.skills.questionnaire.collect import collect_responses
        result = collect_responses(self._make_q(), n=3, fill_mode="real")
        assert result == []

    def test_llm_mode_returns_n_responses(self, tmp_path, monkeypatch):
        from unittest.mock import patch
        from cca.skills.questionnaire import collect as collect_mod
        from cca.skills.questionnaire.collect import QuestionResponse, SurveyResponse
        monkeypatch.setattr(collect_mod, "_db_path", lambda: tmp_path / "test.db")
        fake = SurveyResponse(
            respondent_id="uid-001",
            product_name="测试产品",
            answers=[QuestionResponse(question_id="q1", answer="4")],
        )
        with patch.object(collect_mod, "_autofill", return_value=fake):
            from cca.skills.questionnaire.collect import collect_responses
            result = collect_responses(self._make_q(), n=2, fill_mode="llm")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# challenge_pm tool: AgentSignal structure aligns with the schema
# ---------------------------------------------------------------------------

class TestChallengePmTool:
    def test_returns_valid_agent_signal_json(self):
        from cca.schema import AgentSignal
        from cca.tools.insight_tools import challenge_pm

        result = challenge_pm.invoke({
            "claim": "产品名称有误，App Store 搜不到该应用",
            "evidence": ["scrape_app_store 返回 error: app_not_found"],
        })
        signal = AgentSignal.model_validate_json(result)
        assert signal.from_agent == "insight"
        assert signal.kind == "pm_challenge"

    def test_claim_and_evidence_in_payload(self):
        from cca.schema import AgentSignal
        from cca.tools.insight_tools import challenge_pm

        result = challenge_pm.invoke({
            "claim": "竞品列表不合理",
            "evidence": ["飞书与钉钉不在同一赛道"],
            "requires_debate": True,
        })
        signal = AgentSignal.model_validate_json(result)
        assert signal.payload.claim == "竞品列表不合理"
        assert len(signal.payload.evidence) >= 1
        assert signal.requires_debate is True

    def test_signal_id_is_auto_generated(self):
        from cca.schema import AgentSignal
        from cca.tools.insight_tools import challenge_pm

        r1 = challenge_pm.invoke({"claim": "c1", "evidence": ["e1"]})
        r2 = challenge_pm.invoke({"claim": "c2", "evidence": ["e2"]})
        s1 = AgentSignal.model_validate_json(r1)
        s2 = AgentSignal.model_validate_json(r2)
        assert s1.signal_id != s2.signal_id  # a UUID, unique every time


# ---------------------------------------------------------------------------
# finalize_sentiment tool: UserSentiment validation and output structure
# ---------------------------------------------------------------------------

class TestFinalizeSentimentTool:
    def _valid_sentiment_json(self) -> str:
        from cca.schema import UserSentiment
        return UserSentiment(
            aggregate_rating=4.2,
            rating_review_count=50000,
            rating_source="appstore_cn",
            positive_themes=["协同效率高", "通知及时"],
            negative_themes=["偶发卡顿"],
        ).model_dump_json()

    def test_returns_product_name_and_sentiment(self):
        from cca.tools.insight_tools import finalize_sentiment
        from cca.schema import UserSentiment
        s_json = UserSentiment(
            aggregate_rating=4.1,
            positive_themes=["好用"],
            negative_themes=["卡顿"],
        ).model_dump_json()

        result = json.loads(finalize_sentiment.invoke({
            "product_name": "钉钉",
            "sentiment_json": s_json,
        }))
        assert result["product_name"] == "钉钉"
        assert result["sentiment"]["aggregate_rating"] == 4.1
        assert "好用" in result["sentiment"]["positive_themes"]

    def test_invalid_rating_returns_error_string(self):
        """An out-of-range rating -> returns an LLM-friendly error string (doesn't raise)."""
        from cca.tools.insight_tools import finalize_sentiment

        bad_json = '{"aggregate_rating": 99, "positive_themes": [], "negative_themes": []}'
        result = finalize_sentiment.invoke({"product_name": "X", "sentiment_json": bad_json})
        assert "UserSentiment 校验失败" in result
        assert "aggregate_rating" in result

    def test_string_themes_are_tolerated(self):
        # Doubao's frequent mistake: filling positive_themes with a delimiter-separated string -> should split into an array on the first try, no retry
        from cca.tools.insight_tools import finalize_sentiment
        bad = json.dumps({
            "positive_themes": "性价比高、出餐快",
            "negative_themes": ["口味偏甜"],
        }, ensure_ascii=False)
        result = json.loads(finalize_sentiment.invoke({"product_name": "X", "sentiment_json": bad}))
        assert result["sentiment"]["positive_themes"] == ["性价比高", "出餐快"]

    def test_schema_fields_preserved(self):
        from cca.tools.insight_tools import finalize_sentiment
        from cca.schema import UserSentiment
        s = UserSentiment(
            aggregate_rating=3.5,
            rating_review_count=1000,
            rating_source="appstore_cn",
            positive_themes=["a", "b"],
            negative_themes=["c"],
        )
        result = json.loads(finalize_sentiment.invoke({
            "product_name": "飞书",
            "sentiment_json": s.model_dump_json(),
        }))
        sent = result["sentiment"]
        assert sent["rating_review_count"] == 1000
        assert sent["rating_source"] == "appstore_cn"
        assert sent["positive_themes"] == ["a", "b"]


# ---------------------------------------------------------------------------
# record_key_events tool: list[Fact] validation + LLM-friendly errors
# ---------------------------------------------------------------------------

class TestRecordKeyEventsTool:
    def _valid_events_json(self) -> str:
        return json.dumps([{
            "statement": "总部推 1 元冰杯引流，多地加盟商称单杯亏损拒绝执行",
            "evidence": [{"source_url": "https://news.example.com/a", "snippet": "原文"}],
        }])

    def test_valid_events_pass_through(self):
        from cca.tools.insight_tools import record_key_events
        result = json.loads(record_key_events.invoke({
            "product_name": "蜜雪冰城", "events_json": self._valid_events_json(),
        }))
        assert result["product_name"] == "蜜雪冰城"
        assert "加盟商" in result["key_events"][0]["statement"]

    def test_missing_evidence_returns_error(self):
        # Fact.evidence min_length=1: missing evidence should return an
        # LLM-self-correctable error string, without raising
        from cca.tools.insight_tools import record_key_events
        bad = json.dumps([{"statement": "无证据事件"}])
        result = record_key_events.invoke({"product_name": "X", "events_json": bad})
        assert "evidence" in result

    def test_non_array_returns_error(self):
        from cca.tools.insight_tools import record_key_events
        result = record_key_events.invoke({"product_name": "X", "events_json": "{}"})
        assert "数组" in result

    def test_bare_url_evidence_is_tolerated(self):
        # Doubao's frequent mistake: filling evidence with a bare URL string -> should pass after normalization, no retry
        from cca.tools.insight_tools import record_key_events
        bad_shape = json.dumps([{"statement": "事件", "evidence": ["https://x.com/a"]}])
        result = json.loads(record_key_events.invoke({"product_name": "X", "events_json": bad_shape}))
        assert result["key_events"][0]["evidence"][0]["source_url"] == "https://x.com/a"

    def test_events_passed_as_list_is_tolerated(self):
        # Doubao sometimes passes an array directly instead of a JSON string -> should be tolerated
        from cca.tools.insight_tools import record_key_events
        events = [{"statement": "事件", "evidence": [{"source_url": "https://x.com"}]}]
        result = json.loads(record_key_events.invoke({"product_name": "X", "events_json": events}))
        assert result["key_events"][0]["statement"] == "事件"
