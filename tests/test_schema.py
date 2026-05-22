"""测试 schema.py 中所有模型的字段约束是否符合预期。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.cca.schema import (
    CollectTask,
    Dimension,
    Evidence,
    Fact,
    PricingInfo,
    PricingTier,
    ProductProfile,
    QAResult,
    ReviewSample,
    ReviewUnit,
    SWOT,
    SWOTPoint,
    TaskPlan,
    UserSentiment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evidence() -> Evidence:
    return Evidence(
        source_url="https://www.feishu.cn/product/meeting",
        snippet="飞书视频会议支持最多 300 人同时在线",
        fetched_at="2026-05-22T10:00:00+08:00",
    )


@pytest.fixture
def fact(evidence: Evidence) -> Fact:
    return Fact(
        statement="飞书视频会议最大支持 300 人同时在线",
        evidence=[evidence],
    )


@pytest.fixture
def dimension(fact: Fact) -> Dimension:
    return Dimension(
        name="视频会议参会人数上限",
        category="功能",
        facts=[fact],
        cross_product_note="飞书(300人) > 钉钉(25人免费版)",
    )


@pytest.fixture
def pricing(evidence: Evidence) -> PricingInfo:
    tier = PricingTier(
        name="免费版",
        price_per_user_monthly=0,
        currency="CNY",
        user_limit=None,
        included_features=["即时消息", "视频会议25人"],
        source=evidence,
    )
    return PricingInfo(has_free_tier=True, pricing_model="per_user", tiers=[tier])


@pytest.fixture
def sentiment(evidence: Evidence) -> UserSentiment:
    review = ReviewSample(
        text="通话质量很稳定，基本没有断线",
        rating=5,
        platform="appstore_cn",
        source=evidence,
    )
    return UserSentiment(
        appstore_cn_rating=4.6,
        appstore_cn_review_count=12000,
        appstore_region="cn",
        positive_themes=["通话稳定", "界面简洁"],
        negative_themes=["通知有时延迟"],
        representative_reviews=[review],
        sources=[evidence],
    )


@pytest.fixture
def swot(fact: Fact) -> SWOT:
    stmt = fact.statement
    return SWOT(
        strengths=[SWOTPoint(point="视频会议容量行业领先", supporting_fact_statements=[stmt])],
        weaknesses=[SWOTPoint(point="免费版人数限制明显", supporting_fact_statements=[stmt])],
        opportunities=[SWOTPoint(point="混合办公需求增长", supporting_fact_statements=[stmt])],
        threats=[SWOTPoint(point="Teams 深度绑定 Microsoft 生态", supporting_fact_statements=[stmt])],
    )


@pytest.fixture
def profile(evidence, dimension, pricing, sentiment, swot) -> ProductProfile:
    return ProductProfile(
        product_name="飞书",
        company="字节跳动",
        website="https://www.feishu.cn",
        product_type="企业协作平台",
        target_users="企业级团队，50人以上",
        dimensions=[dimension],
        pricing=pricing,
        sources=[evidence],
        sentiment=sentiment,
        swot=swot,
    )


# ---------------------------------------------------------------------------
# 合法对象构建
# ---------------------------------------------------------------------------

def test_evidence_valid(evidence: Evidence) -> None:
    assert evidence.source_url == "https://www.feishu.cn/product/meeting"


def test_fact_valid(fact: Fact) -> None:
    assert len(fact.evidence) == 1


def test_dimension_valid(dimension: Dimension) -> None:
    assert dimension.category == "功能"


def test_pricing_info_valid(pricing: PricingInfo) -> None:
    assert pricing.has_free_tier is True
    assert pricing.tiers[0].currency == "CNY"


def test_user_sentiment_valid(sentiment: UserSentiment) -> None:
    assert sentiment.appstore_cn_rating == 4.6
    assert sentiment.appstore_cn_review_count == 12000


def test_swot_valid(swot: SWOT) -> None:
    assert len(swot.strengths) == 1


def test_product_profile_full(profile: ProductProfile) -> None:
    assert profile.product_name == "飞书"
    assert profile.swot is not None


def test_qa_result_valid() -> None:
    r = QAResult(product_name="飞书", passed=True)
    assert r.passed is True


def test_task_plan_valid() -> None:
    plan = TaskPlan(
        target_product="飞书",
        competitor_names=["钉钉", "企业微信"],
        collect_tasks=[CollectTask(product_name="钉钉", priority_dimensions=["定价"])],
    )
    assert len(plan.competitor_names) == 2


def test_review_unit_valid() -> None:
    unit = ReviewUnit(
        agent="collector",
        product_name="钉钉",
        status="passed",
        retry_count=0,
    )
    assert unit.status == "passed"


def test_review_unit_analyst_agent_valid() -> None:
    unit = ReviewUnit(agent="analyst", product_name="飞书", status="needs_retry", retry_count=1)
    assert unit.agent == "analyst"


# ---------------------------------------------------------------------------
# 字段约束验证
# ---------------------------------------------------------------------------

def test_fact_rejects_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        Fact(statement="某个结论", evidence=[])


def test_swot_point_rejects_empty_facts() -> None:
    with pytest.raises(ValidationError):
        SWOTPoint(point="某优势", supporting_fact_statements=[])


def test_review_sample_rejects_out_of_range_rating() -> None:
    with pytest.raises(ValidationError):
        ReviewSample(text="好评", rating=6, platform="appstore_cn")


def test_review_sample_rejects_invalid_platform() -> None:
    with pytest.raises(ValidationError):
        ReviewSample(text="好评", rating=5, platform="twitter")


def test_user_sentiment_rejects_out_of_range_rating() -> None:
    with pytest.raises(ValidationError):
        UserSentiment(appstore_cn_rating=5.5)


def test_product_profile_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        ProductProfile(product_name="飞书", data_confidence=1.5)


def test_pricing_info_rejects_invalid_model() -> None:
    with pytest.raises(ValidationError):
        PricingInfo(has_free_tier=True, pricing_model="monthly")


def test_review_unit_rejects_invalid_agent() -> None:
    with pytest.raises(ValidationError):
        ReviewUnit(agent="pm", product_name="钉钉", status="passed", retry_count=0)


def test_review_unit_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ReviewUnit(agent="collector", product_name="钉钉", status="ok", retry_count=0)
