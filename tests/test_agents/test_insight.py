"""Insight Agent 测试。

覆盖：
- NMF 主题提取（无 LLM 依赖）
- BERT 情感分类（mock transformers）
- 问卷缓存（mock SQLite 路径）
- 问卷 fill_mode（real 模式返回空列表）
- 问卷设计 / 格式化 / 匿名化（mock LLM）
- insight_node 输出结构（mock agent）
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cca.skills.questionnaire.anonymize import anonymize_responses
from cca.skills.questionnaire.collect import QuestionResponse, SurveyResponse
from cca.skills.questionnaire.design import Question, Questionnaire
from cca.skills.questionnaire.distribute import format_questionnaire


# ---------------------------------------------------------------------------
# NMF 主题提取
# ---------------------------------------------------------------------------

class TestNmfTopics:
    def _run(self, texts, n=3):
        from cca.utils.nlp_utils import _nmf_topics
        return _nmf_topics(texts, n)

    def test_returns_list_of_strings(self):
        texts = ["协同办公 消息 通知", "视频会议 稳定 卡顿", "定价 免费 套餐", "移动端 体验 好用", "客服 响应 慢"]
        topics = self._run(texts)
        assert isinstance(topics, list)
        assert all(isinstance(t, str) for t in topics)

    def test_respects_n_topics(self):
        texts = ["协同 消息", "视频 稳定", "定价 免费", "移动 体验", "客服 慢"]
        topics = self._run(texts, n=3)
        assert len(topics) == 3

    def test_fewer_texts_than_topics(self):
        texts = ["一条评论"]
        topics = self._run(texts, n=5)
        assert len(topics) == 1  # n_topics 自动裁剪

    def test_empty_texts_returns_empty(self):
        from cca.utils.nlp_utils import _nmf_topics
        assert _nmf_topics([], n_topics=3) == []


# ---------------------------------------------------------------------------
# 问卷格式化
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
# 问卷匿名化
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
# insight_node 集成（mock agent）
# ---------------------------------------------------------------------------

class TestInsightNode:
    def _make_tool_message(self, name: str, content: str):
        from langchain_core.messages import ToolMessage
        return ToolMessage(content=content, name=name, tool_call_id="fake-id")

    def _fake_sentiment(self, product_name: str) -> str:
        from cca.schema import UserSentiment
        s = UserSentiment(
            appstore_cn_rating=4.2,
            positive_themes=["界面简洁", "通知及时"],
            negative_themes=["偶发卡顿"],
        )
        return json.dumps({"product_name": product_name, "sentiment": s.model_dump()})

    def _invoke(self, mock_state):
        msgs = [
            self._make_tool_message("finalize_sentiment", self._fake_sentiment("钉钉")),
            self._make_tool_message("finalize_sentiment", self._fake_sentiment("企业微信")),
        ]
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": msgs}
        with patch("cca.agents.insight.create_react_agent", return_value=mock_agent):
            from cca.agents.insight import insight_node
            return insight_node(mock_state)

    def test_returns_required_keys(self, mock_state):
        result = self._invoke(mock_state)
        for key in ("profiles", "agent_signals", "audit_log"):
            assert key in result

    def test_sentiment_written_to_profiles(self, mock_state):
        result = self._invoke(mock_state)
        assert result["profiles"]["钉钉"]["sentiment"] is not None
        assert result["profiles"]["企业微信"]["sentiment"] is not None

    def test_collector_data_preserved(self, mock_state):
        # insight_node 只返回增量 {"sentiment": ...}，由 _merge_profiles reducer 保留 Collector 字段。
        # 这里模拟 LangGraph 的 reducer 合并行为，验证合并后 dimensions 不丢失。
        from cca.state import _merge_profiles
        result = self._invoke(mock_state)
        merged = _merge_profiles(mock_state["profiles"], result["profiles"])
        assert "dimensions" in merged["钉钉"]
        assert "sentiment" in merged["钉钉"]

    def test_audit_log_records_products(self, mock_state):
        result = self._invoke(mock_state)
        log = result["audit_log"][0]
        assert log["agent"] == "insight"
        assert "钉钉" in log["products"]

    def test_no_signals_by_default(self, mock_state):
        result = self._invoke(mock_state)
        assert result["agent_signals"] == []


# ---------------------------------------------------------------------------
# 问卷缓存（get_or_create_questionnaire）
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
            # 第二次调用，竞品/维度不同，但产品名相同 → 应命中缓存
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
# 问卷 fill_mode
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
# BERT 情感分类
# ---------------------------------------------------------------------------

class TestBertSentiment:
    def test_empty_texts_returns_empty(self):
        from cca.utils.nlp_utils import _bert_sentiment
        result = _bert_sentiment([], "fake-model")
        assert result == {"positive": [], "negative": [], "neutral": []}

    def test_groups_texts_by_label(self):
        import sys
        from unittest.mock import MagicMock, patch
        from cca.utils.nlp_utils import _bert_sentiment

        mock_classifier = MagicMock(return_value=[
            [{"label": "positive", "score": 0.9}],
            [{"label": "negative", "score": 0.85}],
            [{"label": "neutral", "score": 0.7}],
        ])
        fake_transformers = MagicMock()
        fake_transformers.pipeline.return_value = mock_classifier
        with patch.dict(sys.modules, {"transformers": fake_transformers}):
            # 清除缓存避免测试间干扰
            import cca.utils.nlp_utils as nlp_mod
            nlp_mod._bert_pipeline_cache.clear()
            result = _bert_sentiment(["好用", "卡顿", "一般"], "fake-model")

        assert "好用" in result["positive"]
        assert "卡顿" in result["negative"]
        assert "一般" in result["neutral"]

    def test_unknown_label_falls_back_to_neutral(self):
        import sys
        from unittest.mock import MagicMock, patch
        from cca.utils.nlp_utils import _bert_sentiment

        mock_classifier = MagicMock(return_value=[
            [{"label": "LABEL_99", "score": 0.6}],
        ])
        fake_transformers = MagicMock()
        fake_transformers.pipeline.return_value = mock_classifier
        with patch.dict(sys.modules, {"transformers": fake_transformers}):
            import cca.utils.nlp_utils as nlp_mod
            nlp_mod._bert_pipeline_cache.clear()
            result = _bert_sentiment(["模糊评价"], "fake-model")

        assert "模糊评价" in result["neutral"]


# ---------------------------------------------------------------------------
# challenge_pm 工具：AgentSignal 结构与 schema 对齐
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
        assert s1.signal_id != s2.signal_id  # UUID，每次唯一


# ---------------------------------------------------------------------------
# finalize_sentiment 工具：UserSentiment 验证与输出结构
# ---------------------------------------------------------------------------

class TestFinalizeSentimentTool:
    def _valid_sentiment_json(self) -> str:
        from cca.schema import UserSentiment
        return UserSentiment(
            appstore_cn_rating=4.2,
            appstore_cn_review_count=50000,
            appstore_region="cn",
            positive_themes=["协同效率高", "通知及时"],
            negative_themes=["偶发卡顿"],
        ).model_json()

    def test_returns_product_name_and_sentiment(self):
        from cca.tools.insight_tools import finalize_sentiment
        from cca.schema import UserSentiment
        s_json = UserSentiment(
            appstore_cn_rating=4.1,
            positive_themes=["好用"],
            negative_themes=["卡顿"],
        ).model_dump_json()

        result = json.loads(finalize_sentiment.invoke({
            "product_name": "钉钉",
            "sentiment_json": s_json,
        }))
        assert result["product_name"] == "钉钉"
        assert result["sentiment"]["appstore_cn_rating"] == 4.1
        assert "好用" in result["sentiment"]["positive_themes"]

    def test_invalid_rating_returns_error_string(self):
        """rating 越界 → 返回 LLM-friendly 错误字符串（不 raise）。"""
        from cca.tools.insight_tools import finalize_sentiment

        bad_json = '{"appstore_cn_rating": 99, "positive_themes": [], "negative_themes": []}'
        result = finalize_sentiment.invoke({"product_name": "X", "sentiment_json": bad_json})
        assert "UserSentiment 校验失败" in result
        assert "appstore_cn_rating" in result

    def test_schema_fields_preserved(self):
        from cca.tools.insight_tools import finalize_sentiment
        from cca.schema import UserSentiment
        s = UserSentiment(
            appstore_cn_rating=3.5,
            appstore_cn_review_count=1000,
            appstore_region="cn",
            positive_themes=["a", "b"],
            negative_themes=["c"],
        )
        result = json.loads(finalize_sentiment.invoke({
            "product_name": "飞书",
            "sentiment_json": s.model_dump_json(),
        }))
        sent = result["sentiment"]
        assert sent["appstore_cn_review_count"] == 1000
        assert sent["appstore_region"] == "cn"
        assert sent["positive_themes"] == ["a", "b"]


# ---------------------------------------------------------------------------
# _effective_bert_model：微调模型自动切换
# ---------------------------------------------------------------------------

class TestEffectiveBertModel:
    def test_returns_config_model_when_no_finetune_dir(self, tmp_path):
        from unittest.mock import patch
        from cca.tools import insight_tools as it_mod

        with patch.object(it_mod, "PROJECT_ROOT", tmp_path):
            with patch.object(it_mod, "load_config", return_value={
                "nlp": {
                    "bert_model": "lxyuan/distilbert",
                    "fine_tune": {"enabled": True, "model_output_dir": "data/models/ft"},
                }
            }):
                model = it_mod._effective_bert_model()
        assert model == "lxyuan/distilbert"

    def test_returns_finetuned_path_when_dir_exists(self, tmp_path):
        from unittest.mock import patch
        from cca.tools import insight_tools as it_mod

        ft_dir = tmp_path / "data" / "models" / "ft"
        ft_dir.mkdir(parents=True)

        with patch.object(it_mod, "PROJECT_ROOT", tmp_path):
            with patch.object(it_mod, "load_config", return_value={
                "nlp": {
                    "bert_model": "lxyuan/distilbert",
                    "fine_tune": {"enabled": True, "model_output_dir": "data/models/ft"},
                }
            }):
                model = it_mod._effective_bert_model()
        assert model == str(ft_dir)


# ---------------------------------------------------------------------------
# insight_node：task_plan 为 None 时优雅跳过
# ---------------------------------------------------------------------------

class TestInsightNodeGuards:
    def test_skips_when_task_plan_none(self, mock_state):
        from cca.agents.insight import insight_node
        state = {**mock_state, "task_plan": None}
        result = insight_node(state)
        assert result["audit_log"][0]["event"] == "skipped"
