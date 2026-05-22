"""竞品分析系统数据模型。

通用骨架不硬编码行业字段；维度由 Agent 运行时发现；每条结论必须绑定证据。
"""
from __future__ import annotations
from operator import add
from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """单条证据：来源 URL + 支撑该结论的原文片段。"""
    source_url: str
    snippet: str | None = Field(None, description="来源页面中支撑该结论的原文摘录")
    fetched_at: str  # ISO 8601


class Fact(BaseModel):
    """可验证的客观陈述，必须绑定至少一条证据。"""
    statement: str = Field(description="客观事实陈述，不含主观判断，如'飞书视频会议最大支持300人'")
    evidence: list[Evidence] = Field(min_length=1)


class Dimension(BaseModel):
    """单个分析维度，由 dimension_discovery 或 Agent 自主识别。

    category 为开放字符串，典型值：'功能' / '定价' / '用户口碑' / '生态' / '市场定位' / '技术架构'。
    """
    name: str = Field(description="维度名称，如'视频会议人数上限'、'移动端离线能力'")
    category: str
    facts: list[Fact] = Field(default_factory=list)
    cross_product_note: str | None = Field(
        None,
        description="跨产品的事实性对比结论，必须基于 facts 中的数据推导，不引入主观判断"
    )


class PricingTier(BaseModel):
    """单个定价档位，数据来自官网或公开定价页。"""
    name: str
    price_per_user_monthly_cny: float | None = None
    price_per_user_yearly_cny: float | None = None
    user_limit: int | None = Field(None, description="None 表示不限人数")
    included_features: list[str] = Field(default_factory=list)
    source: Evidence | None = None


class PricingInfo(BaseModel):
    """产品完整定价结构。"""
    has_free_tier: bool
    pricing_model: Literal['per_user', 'per_team', 'custom', 'unknown'] = Field(description="定价模式，如按用户数、按团队规模、自定义报价等")
    tiers: list[PricingTier] = Field(default_factory=list)


class ReviewSample(BaseModel):
    """单条用户评论原文。"""
    text: str
    rating: int | None = Field(None, ge=1, le=5)
    platform: Literal['appstore_cn', 'appstore_us', 'zhihu', 'weibo', 'other'] = Field(description="评论来源平台")
    source: Evidence | None = None


class UserSentiment(BaseModel):
    """用户口碑聚合，全部数据须来自公开渠道的客观抓取。"""
    appstore_cn_rating: float | None = Field(None, ge=1, le=5, description="AppStore 中国区实际评分")
    appstore_cn_review_count: int | None = None
    positive_themes: list[str] = Field(
        default_factory=list,
        description="用户好评的主题归纳，如'通知及时'，须有对应评论样本支撑"
    )
    negative_themes: list[str] = Field(
        default_factory=list,
        description="用户槽点的主题归纳，如'通话断线频繁'"
    )
    representative_reviews: list[ReviewSample] = Field(default_factory=list)
    sources: list[Evidence] = Field(default_factory=list)


class SWOTPoint(BaseModel):
    """单条 SWOT 观点，必须关联支撑它的事实陈述。"""
    point: str
    supporting_fact_statements: list[str] = Field(
        min_length=1,
        description="引用 Dimension.facts 中 statement 原文，确保可溯源"
    )


class SWOT(BaseModel):
    strengths: list[SWOTPoint]
    weaknesses: list[SWOTPoint]
    opportunities: list[SWOTPoint]
    threats: list[SWOTPoint]


class ProductProfile(BaseModel):
    """单个产品的竞品分析档案，适用于任意产品领域。

    product_type / target_users 由 Collector 从官网抓取，dimensions 由 Agent 动态填入。
    """
    product_name: str
    company: str | None = None
    website: str | None = None
    product_type: str | None = Field(None, description="产品类型，Agent 从官网内容推断")
    target_users: str | None = Field(None, description="目标用户，来自官网原文")

    # Collector Agent 填写
    dimensions: list[Dimension] = Field(default_factory=list)
    pricing: PricingInfo | None = None
    sources: list[Evidence] = Field(default_factory=list)

    # Insight Agent 填写
    sentiment: UserSentiment | None = None

    # Analyst Agent 填写
    swot: SWOT | None = None

    # QA/PM Agent 填写
    qa_flags: list[str] = Field(default_factory=list, description="未通过的校验项描述详述：如'定价信息与原始数据不一致'")
    data_confidence: float | None = Field(None, ge=0, le=1, description="QA 评定的整体数据可信度")


class QAResult(BaseModel):
    """QA Agent 对单个产品档案的校验结论。"""
    product_name: str
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    note: str | None = None


class CollectTask(BaseModel):
    """PM 分配给 Collector 的单项采集任务。"""
    product_name: str
    target_urls: list[str] = Field(default_factory=list)
    priority_dimensions: list[str] = Field(
        default_factory=list,
        description="本次重点采集的维度提示，来自 DomainPack；为空则由 Agent 自主决定"
    )


class TaskPlan(BaseModel):
    """PM Agent 的任务拆解结果。"""
    target_product: str
    competitor_names: list[str]
    collect_tasks: list[CollectTask]
    rationale: str | None = None


ReviewStatus = Literal["passed", "needs_retry", "forced"]


class ReviewUnit(BaseModel):
    """PM 对某次 (agent, product) 产出的评审判定。

    PM 在 Collector+Insight 并行完成后统一评审一轮；needs_retry 触发返工，
    返工完毕 PM 再次评审 append 新 ReviewUnit；retry_count > 2 时标 forced。
    """
    agent: Literal["collector", "insight"]
    product_name: str
    status: ReviewStatus
    retry_count: int = Field(description="本次评审前该 (agent, product) 已发生的返工次数")
    qa_flags: list[str] = Field(default_factory=list, description="本轮评审写入的问题列表")
    pm_note: str | None = None
    reviewed_at: str | None = None  # ISO 8601


class CCAState(TypedDict):
    """Agent 间共享的工作台。

    profiles 以 product_name 为 key 存 ProductProfile.model_dump()；
    review_state / audit_log / qa_notes 用 add reducer，多节点并发写入自动追加。
    """
    user_query: str
    target_product: str

    competitor_names: list[str]
    task_plan: dict               # TaskPlan.model_dump()

    profiles: dict[str, dict]     # {product_name: ProductProfile.model_dump()}

    # PM 在 Collector+Insight 完成后的评审台账，累加每一轮评审产出
    # status=forced 的项即报告中"未经充分审核"段落的数据源
    review_state: Annotated[list[dict], add]   # list[ReviewUnit.model_dump()]

    qa_results: list[dict]        # 终局 QA Agent 产出（与 PM inline QA 分离）
    report_status: Literal["pending", "passed", "unreviewed"]

    report_md: str | None
    report_pdf_path: str | None

    qa_notes: Annotated[list[str], add]
    audit_log: Annotated[list[dict], add]
