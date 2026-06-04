"""测试 schema.py 中所有模型的字段约束是否符合预期。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cca.schema import (
    SWOT,
    CollectTask,
    DecisionAlternative,
    DecisionRecord,
    Dimension,
    DomainSeed,
    Evidence,
    Fact,
    InitialBrief,
    InitialBriefOutput,
    InsightTask,
    PricingInfo,
    PricingTier,
    ProductProfile,
    QAResult,
    ReportTask,
    ReviewSample,
    ReviewUnit,
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
        aggregate_rating=4.6,
        rating_review_count=12000,
        rating_source="appstore_cn",
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
def profile(evidence, dimension, pricing, sentiment) -> ProductProfile:
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
    assert sentiment.aggregate_rating == 4.6
    assert sentiment.rating_review_count == 12000


def test_swot_valid(swot: SWOT) -> None:
    assert len(swot.strengths) == 1


def test_product_profile_full(profile: ProductProfile) -> None:
    assert profile.product_name == "飞书"
    assert profile.sentiment is not None
    assert profile.pricing is not None


def test_product_profile_has_no_swot_field() -> None:
    """SWOT 已不再是 profile owner 字段——Reporter 工具产出后直接进 MD。"""
    assert "swot" not in ProductProfile.model_fields


def test_product_profile_key_events_default_empty() -> None:
    p = ProductProfile(product_name="蜜雪冰城")
    assert p.key_events == []


def test_product_profile_accepts_key_events(fact: Fact) -> None:
    p = ProductProfile(product_name="蜜雪冰城", key_events=[fact])
    assert p.key_events[0].statement == fact.statement


def test_qa_result_valid() -> None:
    r = QAResult(product_name="飞书", passed=True)
    assert r.passed is True


def test_task_plan_valid() -> None:
    plan = TaskPlan(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信"],
        collect_tasks=[CollectTask(product_name="钉钉", priority_dimensions=["定价"])],
        insight_tasks=[InsightTask(product_name="钉钉", target_platforms=["appstore_cn"])],
    )
    assert len(plan.competitor_names) == 2
    assert plan.product_type == "企业协作平台"


def test_task_plan_rejects_missing_target_product() -> None:
    """target_product 是 PM 入口必填字段。"""
    with pytest.raises(ValidationError):
        TaskPlan(
            product_type="企业协作平台",
            competitor_names=["钉钉"],
            collect_tasks=[],
            insight_tasks=[],
        )


def test_task_plan_rejects_missing_product_type() -> None:
    """product_type 经一轮 debate 收敛后是权威值，必填。"""
    with pytest.raises(ValidationError):
        TaskPlan(
            target_product="飞书",
            competitor_names=["钉钉"],
            collect_tasks=[],
            insight_tasks=[],
        )


def test_insight_task_has_self_extension_flag() -> None:
    """v3：InsightTask 与 CollectTask 对称，有 allow_self_extension。"""
    task = InsightTask(product_name="飞书")
    assert task.allow_self_extension is True


def test_insight_task_default_empty_platforms() -> None:
    """InsightTask 不传 target_platforms 时默认空列表，由 Insight 自主决定。"""
    task = InsightTask(product_name="飞书")
    assert task.target_platforms == []
    assert task.priority_dimensions == []


def test_insight_task_accepts_multiple_platforms() -> None:
    task = InsightTask(
        product_name="飞书",
        target_platforms=["appstore_cn", "zhihu"],
    )
    assert len(task.target_platforms) == 2


def test_insight_task_accepts_open_platform() -> None:
    """target_platforms 是开放字符串：不预设产品领域，任意来源名都接受。"""
    task = InsightTask(product_name="飞书", target_platforms=["twitter", "fragrantica", "tmall"])
    assert task.target_platforms == ["twitter", "fragrantica", "tmall"]


def test_report_task_valid() -> None:
    task = ReportTask(
        target_product="飞书",
        competitors=["钉钉", "企业微信"],
        product_names=["飞书", "钉钉", "企业微信"],
        focus_dimensions=["AI 助手", "视频会议"],
        target_audience="产品负责人",
        sections=["市场定位", "功能对比", "SWOT"],
    )
    assert task.output_formats == ["markdown", "pdf"]
    assert task.invoke_call_report_reviewer is True
    # 原 AnalystTask 字段已合并进 ReportTask
    assert task.require_swot is True
    assert task.cross_product_comparison_required is True


def test_report_task_minimal_has_analyst_defaults() -> None:
    """最简 ReportTask 只填 target_product + competitors，其余字段有默认值。"""
    task = ReportTask(target_product="飞书", competitors=["钉钉"])
    assert task.require_swot is True
    assert task.cross_product_comparison_required is True
    assert task.focus_dimensions == []
    assert task.product_names == []


def test_report_task_rejects_invalid_format() -> None:
    with pytest.raises(ValidationError):
        ReportTask(
            target_product="飞书",
            competitors=["钉钉"],
            output_formats=["ppt"],
        )


def test_review_unit_valid() -> None:
    unit = ReviewUnit(
        agent="collector",
        product_name="钉钉",
        status="passed",
        retry_count=0,
    )
    assert unit.status == "passed"


def test_review_unit_rejects_analyst_agent() -> None:
    """Analyst 已并入 Reporter，agent 字段不再接受 'analyst'。"""
    with pytest.raises(ValidationError):
        ReviewUnit(agent="analyst", product_name="飞书", status="needs_retry", retry_count=1)


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


def test_review_sample_accepts_open_platform() -> None:
    """platform 是开放字符串：电商 / 垂类 / 任意来源名都接受。"""
    sample = ReviewSample(text="好评", rating=5, platform="fragrantica")
    assert sample.platform == "fragrantica"


def test_user_sentiment_rejects_out_of_range_rating() -> None:
    with pytest.raises(ValidationError):
        UserSentiment(aggregate_rating=5.5)


def test_product_profile_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        ProductProfile(product_name="飞书", data_confidence=1.5)


# ---------------------------------------------------------------------------
# DecisionRecord
# ---------------------------------------------------------------------------


def test_decision_record_minimal_valid() -> None:
    record = DecisionRecord(
        phase="task_plan",
        decision_type="competitor_selection",
        chosen={"competitors": ["钉钉", "企业微信"]},
        rationale="基于 exploration_result 中头部市占率确定",
        ts="2026-05-25T10:00:00+08:00",
    )
    assert record.decision_id.startswith("D-")
    assert record.alternatives_considered == []
    assert record.inputs_used == []


def test_decision_record_full_fields() -> None:
    record = DecisionRecord(
        phase="task_plan",
        decision_type="competitor_selection",
        chosen={"competitors": ["钉钉", "企业微信"]},
        alternatives_considered=[
            DecisionAlternative(
                option="腾讯会议",
                rejected_reason="赛道偏视频会议工具，与协作平台主线不对齐",
            ),
        ],
        rationale="头部市占率 + 同协作平台赛道",
        inputs_used=[
            "exploration_result.competitor_names",
            "exploration_result.product_type",
        ],
        ts="2026-05-25T10:00:00+08:00",
    )
    assert len(record.alternatives_considered) == 1
    assert record.alternatives_considered[0].option == "腾讯会议"
    assert len(record.inputs_used) == 2


def test_decision_record_id_unique_across_instances() -> None:
    a = DecisionRecord(
        phase="initial_brief",
        decision_type="other",
        chosen={},
        rationale="x",
        ts="2026-05-25T10:00:00+08:00",
    )
    b = DecisionRecord(
        phase="initial_brief",
        decision_type="other",
        chosen={},
        rationale="x",
        ts="2026-05-25T10:00:00+08:00",
    )
    assert a.decision_id != b.decision_id


def test_decision_record_rejects_invalid_phase() -> None:
    with pytest.raises(ValidationError):
        DecisionRecord(
            phase="phase_x",  # type: ignore[arg-type]
            decision_type="other",
            chosen={},
            rationale="x",
            ts="2026-05-25T10:00:00+08:00",
        )


def test_decision_record_requires_rationale() -> None:
    with pytest.raises(ValidationError):
        DecisionRecord(
            phase="task_plan",
            decision_type="other",
            chosen={},
            ts="2026-05-25T10:00:00+08:00",
        )  # type: ignore[call-arg]


def test_pricing_info_coerces_invalid_model_to_unknown() -> None:
    """采集期放松：非法 pricing_model 不再 raise，归一到 unknown。"""
    p = PricingInfo(has_free_tier=True, pricing_model="monthly")
    assert p.pricing_model == "unknown"


def test_review_unit_rejects_invalid_agent() -> None:
    with pytest.raises(ValidationError):
        ReviewUnit(agent="pm", product_name="钉钉", status="passed", retry_count=0)


def test_review_unit_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ReviewUnit(agent="collector", product_name="钉钉", status="ok", retry_count=0)


# ---------------------------------------------------------------------------
# DomainSeed + InitialBriefOutput.domain_seed
# ---------------------------------------------------------------------------


def test_domain_seed_minimal_valid() -> None:
    seed = DomainSeed(source_files=["uploads/x.pdf"])
    assert seed.source_files == ["uploads/x.pdf"]
    assert seed.dimension_candidates == []
    assert seed.competitor_mentions == []
    assert seed.product_type_hint is None
    assert seed.terminology == {}


def test_domain_seed_with_all_fields() -> None:
    seed = DomainSeed(
        source_files=["uploads/m.pdf"],
        dimension_candidates=["视频会议", "AI 助手"],
        competitor_mentions=["钉钉", "企业微信"],
        product_type_hint="协同办公平台",
        terminology={"DAU": "日活跃用户"},
    )
    assert len(seed.dimension_candidates) == 2
    assert seed.product_type_hint == "协同办公平台"


def test_domain_seed_rejects_too_many_dimensions() -> None:
    """dimension_candidates 上限 20 项。"""
    with pytest.raises(ValidationError):
        DomainSeed(
            source_files=["uploads/m.pdf"],
            dimension_candidates=[f"d{i}" for i in range(21)],
        )


def test_initial_brief_output_domain_seed_optional() -> None:
    """domain_seed 字段是可选的，None 时不影响其他字段。"""
    out = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书", company_hint=None, user_query="x",
        ),
        decision_records=[
            DecisionRecord(
                phase="initial_brief",
                decision_type="other",
                chosen={},
                rationale="x",
            ),
        ],
    )
    assert out.domain_seed is None


def test_initial_brief_output_with_domain_seed() -> None:
    out = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书", company_hint=None, user_query="x",
        ),
        decision_records=[
            DecisionRecord(
                phase="initial_brief",
                decision_type="other",
                chosen={},
                rationale="x",
            ),
        ],
        domain_seed=DomainSeed(source_files=["uploads/x.pdf"]),
    )
    assert out.domain_seed is not None
    assert out.domain_seed.source_files == ["uploads/x.pdf"]
