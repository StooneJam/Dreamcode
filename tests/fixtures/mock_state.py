"""Report Agent 开发用 mock CCAState —— 模拟 Phase 2 结束后 PM 下发 ReportTask 的时刻。"""
from __future__ import annotations

from cca.schema import (
    AnalystTask,
    CollectTask,
    Dimension,
    Evidence,
    Fact,
    InsightTask,
    PricingInfo,
    PricingTier,
    ProductProfile,
    ReportTask,
    ReviewSample,
    ReviewUnit,
    SWOT,
    SWOTPoint,
    TaskPlan,
    UserSentiment,
)
from cca.state import CCAState


def _evidence(url: str, snippet: str) -> Evidence:
    return Evidence(source_url=url, snippet=snippet, fetched_at="2026-05-23T00:00:00Z")


def _make_profile(name: str, rating: float, price: float) -> dict:
    ev = _evidence(f"https://{name}.com/pricing", f"{name} Pro {price}元/用户/月")
    fact = Fact(statement=f"{name} Pro 版按用户每月 {price} 元", evidence=[ev])
    dimension = Dimension(
        name="视频会议人数上限",
        category="功能",
        facts=[fact],
        cross_product_note=f"{name} 最大支持 300 人视频会议",
    )
    pricing = PricingInfo(
        has_free_tier=True,
        pricing_model="per_user",
        tiers=[PricingTier(name="Pro", price_per_user_monthly=price, currency="CNY")],
    )
    sentiment = UserSentiment(
        appstore_cn_rating=rating,
        appstore_cn_review_count=12000,
        positive_themes=["界面简洁", "通知及时"],
        negative_themes=["偶发卡顿", "视频会议掉线"],
        representative_reviews=[
            ReviewSample(text="整体好用，偶尔视频掉线", rating=4, platform="appstore_cn")
        ],
    )
    swot = SWOT(
        strengths=[SWOTPoint(
            point="定价低于竞品均值",
            supporting_fact_statements=[f"{name} Pro 版按用户每月 {price} 元"],
        )],
        weaknesses=[SWOTPoint(
            point="移动端稳定性有待提升",
            supporting_fact_statements=["偶发卡顿"],
        )],
        opportunities=[SWOTPoint(
            point="AI 集成场景增长",
            supporting_fact_statements=[f"{name} Pro 版按用户每月 {price} 元"],
        )],
        threats=[SWOTPoint(
            point="头部厂商竞争加剧",
            supporting_fact_statements=["偶发卡顿"],
        )],
    )
    return ProductProfile(
        product_name=name,
        company=f"{name} Inc.",
        website=f"https://{name}.com",
        product_type="协作办公SaaS",
        target_users="中小企业团队",
        dimensions=[dimension],
        pricing=pricing,
        sentiment=sentiment,
        swot=swot,
        sources=[ev],
    ).model_dump()


def make_mock_state(invoke_reviewer: bool = False) -> CCAState:
    """构造完整 CCAState，代表 PM 完成 Phase 2 QA 并下发 ReportTask 后的状态。

    企业微信的 collector 数据被标为 forced（retry>2），用于验证置信度标注逻辑。
    """
    profiles = {
        "钉钉": _make_profile("钉钉", rating=4.2, price=30.0),
        "企业微信": _make_profile("企业微信", rating=3.9, price=25.0),
    }
    report_task = ReportTask(
        target_product="飞书",
        competitors=["钉钉", "企业微信"],
        output_formats=["markdown", "pdf"],
        target_audience="产品负责人",
        sections=["执行摘要", "核心功能对比", "定价结构", "用户口碑", "SWOT 分析", "结论与建议"],
        invoke_call_report_reviewer=invoke_reviewer,
    )
    review_state = [
        ReviewUnit(agent="collector", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(
            agent="collector", product_name="企业微信", status="forced", retry_count=3,
            qa_flags=["定价来源 404，数据不完整"],
        ).model_dump(),
        ReviewUnit(agent="insight", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(agent="insight", product_name="企业微信", status="passed", retry_count=1).model_dump(),
        ReviewUnit(agent="analyst", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(agent="analyst", product_name="企业微信", status="passed", retry_count=0).model_dump(),
    ]
    return CCAState(
        user_query="帮我分析飞书的主要竞品钉钉和企业微信",
        target_product="飞书",
        competitor_names=["钉钉", "企业微信"],
        task_plan=TaskPlan(
            target_product="飞书",
            product_type="协作办公SaaS",
            competitor_names=["钉钉", "企业微信"],
            collect_tasks=[CollectTask(product_name="钉钉"), CollectTask(product_name="企业微信")],
            insight_tasks=[InsightTask(product_name="钉钉"), InsightTask(product_name="企业微信")],
        ).model_dump(),
        analyst_task=AnalystTask(
            target_products=["钉钉", "企业微信"],
            focus_dimensions=["视频会议人数上限", "定价"],
            require_swot=True,
        ).model_dump(),
        report_task=report_task.model_dump(),
        profiles=profiles,
        review_state=review_state,
        qa_results=[],
        report_status="pending",
        report_md=None,
        report_pdf_path=None,
        qa_notes=["企业微信定价数据来源不稳定，已 forced 放行"],
        audit_log=[],
    )
