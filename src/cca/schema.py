"""
竞品分析系统数据模型
通用骨架不硬编码行业字段；维度由 Agent 运行时发现；每条结论必须绑定证据。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 三家族标识，用于 debate 类型约束
AgentFamily = Literal["gpt-5", "deepseek", "doubao"]


class Evidence(BaseModel):
    """单条证据：来源 URL + 支撑该结论的原文片段。"""
    source_url: str
    snippet: str | None = Field(None, description="来源页面中支撑该结论的原文摘录")
    fetched_at: str = Field(description="ISO 8601 时间戳")


class Fact(BaseModel):
    """可验证的客观陈述，必须绑定至少一条证据。"""
    statement: str = Field(description="客观事实陈述，不含主观判断，如'飞书视频会议最大支持300人'")
    evidence: list[Evidence] = Field(min_length=1)


class Dimension(BaseModel):
    """
    单个分析维度，由 dimension_discovery 或 Agent 自主识别。
    category 为开放字符串，典型值：'功能' / '定价' / '用户口碑' / '生态' / '市场定位' / '技术架构'。
    """
    name: str = Field(description="维度名称，如'视频会议人数上限'、'移动端离线能力'")
    category: str
    facts: list[Fact] = Field(default_factory=list)
    cross_product_note: str | None = Field(
        None,
        description="跨产品的事实性对比结论，必须基于 facts 中的数据推导，不引入主观判断",
    )


class PricingTier(BaseModel):
    """单个定价档位，数据来自官网或公开定价页。"""
    name: str
    price_per_user_monthly: float | None = None
    price_per_user_yearly: float | None = None
    currency: str | None = Field(None, description="ISO 4217 货币代码，如 'CNY'、'USD'、'EUR'")
    user_limit: int | None = Field(None, description="None 表示不限人数")
    included_features: list[str] = Field(default_factory=list)
    source: Evidence | None = None


class PricingInfo(BaseModel):
    """产品完整定价结构。"""
    has_free_tier: bool
    pricing_model: Literal["per_user", "per_team", "custom", "unknown"] = Field(
        description="定价模式，如按用户数、按团队规模、自定义报价等",
    )
    tiers: list[PricingTier] = Field(default_factory=list)


class ReviewSample(BaseModel):
    """单条用户评论原文。"""
    text: str
    rating: int | None = Field(None, ge=1, le=5)
    platform: Literal["appstore_cn", "appstore_us", "zhihu", "weibo", "other"] = Field(
        description="评论来源平台",
    )
    source: Evidence | None = None


class UserSentiment(BaseModel):
    """用户口碑聚合，全部数据须来自公开渠道的客观抓取。"""
    appstore_cn_rating: float | None = Field(None, ge=1, le=5, description="AppStore 实际评分")
    appstore_cn_review_count: int | None = None
    appstore_region: str | None = Field(None, description="评分所在区域，如 'cn'、'us'、'global'")
    positive_themes: list[str] = Field(
        default_factory=list,
        description="用户好评的主题归纳，如'通知及时'，须有对应评论样本支撑",
    )
    negative_themes: list[str] = Field(
        default_factory=list,
        description="用户槽点的主题归纳，如'通话断线频繁'",
    )
    representative_reviews: list[ReviewSample] = Field(default_factory=list)
    sources: list[Evidence] = Field(default_factory=list)


class SWOTPoint(BaseModel):
    """单条 SWOT 观点，必须关联支撑它的事实陈述。"""
    point: str
    supporting_fact_statements: list[str] = Field(
        min_length=1,
        description="引用 Dimension.facts 中 statement 原文，确保可溯源",
    )


class SWOT(BaseModel):
    """SWOT 四象限：每个象限是 SWOTPoint 列表。"""
    strengths: list[SWOTPoint]
    weaknesses: list[SWOTPoint]
    opportunities: list[SWOTPoint]
    threats: list[SWOTPoint]


class ProductProfile(BaseModel):
    """
    单个产品的竞品分析档案，适用于任意产品领域。
    填写时序：
        1. PM 起草：product_name 必填；company 可选 hint
        2. Collector 联网验证 + 填实：product_type / target_users / dimensions / pricing / sources / website
           Collector 可挑战 PM 的 hint，通过 debate 修正
        3. Insight 填：sentiment
        4. Analyst 填：swot
        5. PM debate-review 填：qa_flags / data_confidence
    """

    # PM Agent 起草（凭训练知识；company 是 hint，Collector 可挑战）
    product_name: str
    company: str | None = Field(None, description="PM 训练知识 seed，Collector 联网验证")

    # Collector Agent 联网验证 + 填实
    product_type: str | None = Field(None, description="Collector 联网推断，PM debate 收敛")
    target_users: str | None = Field(None, description="目标用户，来自官网原文")
    website: str | None = Field(None, description="官网 URL，Collector 联网查找")
    dimensions: list[Dimension] = Field(default_factory=list)
    pricing: PricingInfo | None = None
    sources: list[Evidence] = Field(default_factory=list)

    # Insight Agent 填写
    sentiment: UserSentiment | None = None

    # Analyst Agent 填写
    swot: SWOT | None = None

    # PM debate-review 填写
    qa_flags: list[str] = Field(
        default_factory=list,
        description="未通过的校验项描述，如'定价信息与原始数据不一致'",
    )
    data_confidence: float | None = Field(
        None,
        ge=0,
        le=1,
        description="PM 评定的整体数据可信度",
    )


class QAResult(BaseModel):
    """QA Agent 对单个产品档案的校验结论。"""
    product_name: str
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    note: str | None = None


# PM 一轮下发 Collector 的初版分析简报，指导 Collector 的联网探索；Collector 可接受也可挑战
class InitialBrief(BaseModel):
    """
    PM 拿到用户输入后起草的初版分析简报，指导 Collector一轮输出。
    """
    target_product: str
    company_hint: str | None = Field(None, description="PM 凭训练知识给的公司 seed，Collector 可挑战")
    user_query: str = Field(description="原始用户输入，给collector理解意图")
    rationale: str | None = None

class ProductBrief(BaseModel):
    """Collector 第一轮粗探索产出的最小竞品档案。"""
    product_name: str
    company: str | None = None
    website: str | None = None
    product_type: str | None = None

class CollectorExplorationResult(BaseModel):
    """
    Collector 第一轮 ReAct 联网探索的产出。
    经 PM debate 收敛后写回 state，作为 PM 阶段二 TaskPlan 的输入。
    """
    target_product: str
    product_type: str = Field(description="Collector 联网推断的产品赛道")
    competitor_names: list[str] = Field(description="Collector 联网发现的主要竞品")
    discovered_dimensions: list[str] = Field(description="Collector 联网总结的对比维度候选")
    initial_profiles: list[ProductBrief] = Field(
        description="一轮输出，包括product_name，company，website，product_type"
    )
    rationale: str | None = None


# PM 二轮下发 Collector/Insight 的任务细化，指导下一轮产出；Collector/Insight 可接受也可挑战
class CollectTask(BaseModel):
    """PM 分配给 Collector 的单项采集任务。"""
    product_name: str
    priority_dimensions: list[str] = Field(
        default_factory=list,
        description="PM 根据产品类型和 DomainPack 确定的重点维度；为空则由 Collector 自主判断",
    )
    allow_self_extension: bool = Field(
        True,
        description="Collector 可否自主追加搜索/抓取",
    )


class InsightTask(BaseModel):
    """PM 分配给 Insight 的单项分析任务。"""
    product_name: str
    target_platforms: list[Literal["appstore_cn", "appstore_us", "zhihu", "weibo", "other"]] = Field(
        default_factory=list,
        description="PM 凭训练知识给 hint，Insight 可拒绝 / 扩展 / 替换；为空则由 Insight 自主决定",
    )
    priority_dimensions: list[str] = Field(
        default_factory=list,
        description="PM 根据产品类型和 DomainPack 确定的重点维度；为空则由 Insight 自主判断",
    )
    allow_self_extension: bool = Field(
        True,
        description="Insight 可否自主追加平台/主题",
    )


class TaskPlan(BaseModel):
    """
    PM 阶段二：基于 CollectorExplorationResult 给 Collector 和 Insight 下发的细粒度任务包
    """
    target_product: str
    product_type: str = Field(description="一轮 debate 收敛后的权威产品类型")
    competitor_names: list[str] = Field(description="一轮debate 收敛后的权威竞品列表")
    collect_tasks: list[CollectTask]
    insight_tasks: list[InsightTask]
    rationale: str | None = None


# PM 三轮下发 Analyst 的分析任务细化，指导下一轮产出；Analyst 可接受也可挑战
class AnalystTask(BaseModel):
    """PM 阶段三：Collector+Insight QA 通过后下发的分析任务。"""
    product_names: list[str] = Field(description="参与对比的产品名，通常 = competitor_names + target_product")
    focus_dimensions: list[str] = Field(
        default_factory=list,
        description="重点对比维度，PM 根据 Collector+Insight 产出指定高亮维度",
    )
    require_swot: bool = True
    cross_product_comparison_required: bool = Field(
        True,
        description="是否要求生成跨竞品横向对比",
    )

# PM 四轮下发 Report 的分析任务细化，指导下一轮产出。
class ReportTask(BaseModel):
    """PM 阶段四：Analyst QA 通过后下发的报告撰写任务。"""
    product_names: list[str] = Field(description="参与对比的产品名，通常 = competitor_names + target_product")
    output_formats: list[Literal["markdown", "pdf"]] = Field(
        default_factory=lambda: ["markdown", "pdf"],
    )
    target_audience: str | None = Field(
        None,
        description="读者类型，如'产品负责人'、'技术评审'，影响 Reporter 语气",
    )
    sections: list[str] = Field(
        default_factory=list,
        description="报告应含章节；为空则由 Reporter 自主组织",
    )
    invoke_call_report_reviewer: bool = Field(
        True,
        description="是否调用 call_report_reviewer skill（Doubao + DeepSeek debate 终审）",
    )


# review 结果：PM 对 Collector/Insight/Analyst 产出的评审结论，包含返工建议和 QA 结果；用于 PM 自身记录和后续分析，也可供用户查询了解 PM 的评审逻辑
ReviewStatus = Literal["passed", "needs_retry", "forced"]


class ReviewUnit(BaseModel):
    """
    PM 对某次 (agent, product) 产出的评审判定。
    PM 在 Collector+Insight 并行完成后统一评审一轮；needs_retry 触发返工，
    返工完毕 PM 再次评审 append 新 ReviewUnit；retry_count > 2 时标 forced。
    """
    agent: Literal["collector", "insight", "analyst"]
    product_name: str
    status: ReviewStatus
    retry_count: int = Field(description="本次评审前该 (agent, product) 已发生的返工次数")
    qa_flags: list[str] = Field(
        default_factory=list,
        description="未通过的校验项描述，如'定价信息与原始数据不一致'",
    )
    pm_note: str | None = None
    reviewed_at: str | None = Field(None, description="ISO 8601 时间戳")



# debate 应用于 3 个 checkpoint：
#    1. PM 二轮 TaskPlan（精化竞品 / 产品类型）
#    2. PM 三轮 AnalystTask 后的 SWOT 校验
#    3. Report 终审（call_report_reviewer skill）

class DebatePosition(BaseModel):
    """4 阶段 debate 中单个辩方在某一轮的观点。"""
    agent_family: AgentFamily
    claim: str = Field(description="辩方的核心主张")
    evidence: list[str] = Field(min_length=1, description="支撑 claim 的事实/引用，至少 1 条")


class DebateRound(BaseModel):
    """debate 单轮：双方独立给观点 → 互相批驳 → 修订。"""
    round: int = Field(description="第几轮，从 1 开始")
    positions: list[DebatePosition]
    critiques: dict[AgentFamily, str] = Field(
        description="每个辩方对其他方观点的批驳，key ：被批驳方的家族名",
    )
    refinements: dict[AgentFamily, str] = Field(
        description="每个辩方看到批驳后的修订观点，key ：修订方的家族名",
    )


class DebateResult(BaseModel):
    """完整 debate 结果：N 轮 + 第三家族仲裁。"""
    target: Literal["pm_taskplan", "analyst_swot", "report"] = Field(description="被审对象类型")
    rounds: list[DebateRound]
    final_verdict: Literal["accepted", "rejected", "accepted_with_revision"]
    judge_family: AgentFamily = Field(description="仲裁方家族，应异于两个辩方")
    judge_rationale: str
    revised_output: dict | None = Field(
        None,
        description="若 verdict 是 accepted_with_revision，给出修订版内容",
    )


# Collector/Insight/Analyst 主动向 PM 表达需求或挑战

class AgentSignal(BaseModel):
    """
    Agent 反向通道信号。
    事实性信号（kind=data_gap）走 PM 普通响应；
    主观判断信号（requires_debate=True）触发 PM 启动 debate。
    """
    from_agent: Literal["collector", "insight", "analyst"]
    kind: Literal["data_gap", "pm_challenge", "insight_lead", "other"]
    target: str = Field(description="信号所指的 task_id 或 agent 名")
    payload: dict = Field(description="信号正文，结构因 kind 而异")
    requires_debate: bool = Field(
        False,
        description="主观判断时 True，触发跨家族 debate；事实性信号 False",
    )
    ts: str = Field(description="ISO 8601 时间戳")
