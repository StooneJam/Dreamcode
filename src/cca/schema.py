"""
竞品分析系统数据模型
通用骨架不硬编码行业字段；维度由 Agent 运行时发现；每条结论必须绑定证据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _now_iso() -> str:
    """当前时刻 ISO 8601 UTC 时间戳，供 default_factory 用。"""
    return datetime.now(UTC).isoformat()

# 三家族标识，用于 debate 类型约束
AgentFamily = Literal["gpt-5", "deepseek", "doubao"]


class Evidence(BaseModel):
    """单条证据：来源 URL + 支撑该结论的原文片段。"""

    source_url: str
    snippet: str | None = Field(None, description="来源页面中支撑该结论的原文摘录")
    fetched_at: str = Field(
        default_factory=_now_iso,
        description="ISO 8601 时间戳，默认填写当前时刻",
    )


class Fact(BaseModel):
    """可验证的客观陈述，必须绑定至少一条证据。"""

    statement: str = Field(description="客观事实陈述，不含主观判断，如'飞书视频会议最大支持300人'")
    evidence: list[Evidence] = Field(min_length=1)


class Dimension(BaseModel):
    """
    单个分析维度，由 domain_seed_node 蒸馏（用户上传文档）或 Collector 联网发现。
    category 为开放字符串，典型值：'功能' / '定价' / '用户口碑' / '生态' / '市场定位' / '技术架构'。
    """

    name: str = Field(description="维度名称，如'视频会议人数上限'、'移动端离线能力'")
    category: str = ""  # 采集期放松：开放分类、模型常漏，缺失不该毁掉整个维度
    facts: list[Fact] = Field(default_factory=list)
    cross_product_note: str | None = Field(
        None,
        description="跨产品的事实性对比结论，必须基于 facts 中的数据推导，不引入主观判断",
    )


class PricingTier(BaseModel):
    """单个定价档位，数据来自官网或公开定价页。

    采集期宽松：无价格数字的档位也允许（报告边界再决定是否纳入成本对比）。
    """

    name: str
    price_per_user_monthly: float | None = None
    price_per_user_yearly: float | None = None
    currency: str | None = Field(None, description="ISO 4217 货币代码，如 'CNY'、'USD'、'EUR'")
    user_limit: int | None = Field(None, description="None 表示不限人数")
    included_features: list[str] = Field(default_factory=list)
    source: Evidence | None = None


class PricingInfo(BaseModel):
    """产品完整定价结构。采集期放松：has_free_tier 可缺省，非法 pricing_model 归 unknown。"""

    has_free_tier: bool | None = None
    pricing_model: Literal["per_user", "per_team", "custom", "unknown"] = "unknown"
    tiers: list[PricingTier] = Field(default_factory=list)

    @field_validator("pricing_model", mode="before")
    @classmethod
    def _coerce_unknown_model(cls, v: object) -> object:
        """模型常给枚举外的值；归一到 unknown，不让单字段毁掉整段 pricing。"""
        return v if v in {"per_user", "per_team", "custom", "unknown"} else "unknown"


class ReviewSample(BaseModel):
    """单条用户评论原文。"""

    text: str
    rating: int | None = Field(None, ge=1, le=5)
    platform: str = Field(
        default="other",
        description=(
            "评论来源平台，开放字符串：不预设产品领域。"
            "App 'appstore_cn'/'appstore_us'，社交 'zhihu'/'weibo'，电商 'tmall'/'jd'/'amazon'，"
            "垂类/专业测评站或任意自定义来源名；未知填 'other'"
        ),
    )
    source: Evidence | None = None


class UserSentiment(BaseModel):
    """用户口碑聚合，全部数据须来自公开渠道的客观抓取。"""

    aggregate_rating: float | None = Field(
        None, ge=1, le=5,
        description="渠道聚合评分，统一归一到 1–5（App Store 评分 / 电商星级 / 垂类评分皆可）",
    )
    rating_review_count: int | None = Field(None, description="评分对应的评论/打分样本量")
    rating_source: str | None = Field(
        None,
        description="评分来源渠道，开放字符串，如 'appstore_cn' / 'tmall' / 'jd' / 'amazon' / 'fragrantica'",
    )
    positive_themes: list[str] = Field(
        default_factory=list,
        description="用户好评的主题归纳，由 LLM 直接研判正面评论后归纳",
    )
    negative_themes: list[str] = Field(
        default_factory=list,
        description="用户槽点的主题归纳，由 LLM 直接研判负面评论后归纳",
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
        4. PM debate-review 填：qa_flags / data_confidence

    SWOT 不再是 profile owner 字段 —— Reporter 在生成报告时通过工具产出，直接写入 MD，
    不回写到 state.profiles。
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
    key_events: list[Fact] = Field(
        default_factory=list,
        description="关键事件与经营矛盾/利益冲突语料，客观陈述+证据；因果定性交 Report",
    )

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
    company_hint: str | None = Field(
        None, description="PM 凭训练知识给的公司 seed，Collector 可挑战"
    )
    user_query: str = Field(description="原始用户输入，给collector理解意图")


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
    target_platforms: list[str] = Field(
        default_factory=list,
        description=(
            "PM 给的数据源 hint，开放字符串（App Store / 电商 / 垂类社区 / 任意来源名），"
            "不预设产品领域；Insight 可拒绝 / 扩展 / 替换；为空则由 Insight 自主决定"
        ),
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
    tentative_buckets: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "PM 预设的 canonical bucket 列表，≤8，作为 Collector/Insight 采集时的软引导，"
            "并供 Reporter 阶段 dimension_canonical_map 语义对齐时优先沿用。"
            "非强制：维度对齐由 Reporter 语义归并负责，采集不被 bucket 命名绑架。"
        ),
    )


# PM 三轮下发 Report 的分析 + 撰写任务。原 AnalystTask 字段（focus_dimensions /
# require_swot / cross_product_comparison_required）已合并进此处——Reporter ReAct
# 同时承担横向排序、SWOT 分析与正文撰写。
class ReportTask(BaseModel):
    """PM 阶段三：Collector+Insight QA 通过后下发的分析 + 报告任务。"""

    target_product: str = Field(description="目标分析产品")
    competitors: list[str] = Field(description="竞品名称列表")
    product_names: list[str] = Field(
        default_factory=list,
        description=(
            "参与对比的产品名，通常 = [target_product] + competitors。"
            "用于 dimension_ranking / SWOT 工具确定覆盖范围；为空时由 Reporter 自行推断"
        ),
    )
    focus_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "PM 指定的高亮对比维度。Reporter 据此决定 submit_dimension_ranking 覆盖哪些维度；"
            "为空时由 Reporter 自主判断"
        ),
    )
    require_swot: bool = Field(
        True,
        description="是否要求 Reporter 调 finalize_swot 工具产 SWOT 段落",
    )
    cross_product_comparison_required: bool = Field(
        True,
        description="是否要求生成跨竞品横向对比章节",
    )
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
        description="是否调用 call_report_reviewer skill（Doubao 终审）；默认开启，始终执行且只执行一次",
    )
    dimension_canonical_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "profiles[*].dimensions[*].name → canonical bucket 的映射。PM 阶段三基于真实采集到的 "
            "dim 名产出；代码层校验覆盖率 100%，缺漏自动归 '其他' 桶。Reporter 据此按 bucket 横向排名。"
        ),
    )


# review 结果：PM 对 Collector/Insight 产出的评审结论，包含返工建议和 QA 结果；用于 PM 自身记录和后续分析，也可供用户查询了解 PM 的评审逻辑
ReviewStatus = Literal["passed", "needs_retry", "forced"]


class ReviewUnit(BaseModel):
    """
    PM 对某次 (agent, product) 产出的评审判定。
    PM 在 Collector+Insight 并行完成后统一评审一轮；needs_retry 触发返工，
    返工完毕 PM 再次评审 append 新 ReviewUnit；retry_count > 2 时标 forced。
    """

    agent: Literal["collector", "insight"]
    product_name: str
    status: ReviewStatus
    retry_count: int = Field(description="本次评审前该 (agent, product) 已发生的返工次数")
    qa_flags: list[str] = Field(
        default_factory=list,
        description="未通过的校验项描述，如'定价信息与原始数据不一致'",
    )
    pm_note: str | None = None
    reviewed_at: str | None = Field(None, description="ISO 8601 时间戳")


class HumanReviewFeedback(BaseModel):
    """用户在 phase 2.5 对 Collector/Insight 产出的一次性自由文本修订意见。

    前端只给一个文本框（降低认知成本），不预分类——分栏（哪些针对采集、
    哪些针对情感分析、哪些是竞品增删）由 PM 在 review / 重排时自行解析。
    """

    raw_feedback: str | None = Field(None, description="用户原文修订意见，不预分类")
    approved: bool = Field(False, description="True = 无修订，直接放行")

    def has_revisions(self) -> bool:
        """是否有需 PM 采纳的实质修订（approved 直接放行不算）。"""
        return not self.approved and bool(self.raw_feedback and self.raw_feedback.strip())


# 决策档案：PM 每阶段产出 task 时同步落盘"为什么这么决定"，
# 支撑离线 Q&A（用户问"为什么选这几家竞品"）+ debate defense（PM 应辩时回读 rationale）


class DecisionAlternative(BaseModel):
    """考虑过但被拒绝的备选项。"""

    option: str = Field(description="备选项内容，如'腾讯会议'、'按维度优先级 A 方案'")
    rejected_reason: str = Field(description="为什么没选这个，一句话讲清拒绝逻辑")


class DecisionRecord(BaseModel):
    """
    PM 单次决策档案。一个 phase 通常含多条 DecisionRecord（如 task_plan 阶段
    同时决定竞品列表 / 维度优先级 / 任务分配，应拆 3 条而非塞进一条）。
    """

    decision_id: str = Field(
        default_factory=lambda: f"D-{uuid4().hex[:8]}",
        description="决策唯一标识，可被报告段落引用（如脚注 [D-a1b2c3d4]）",
    )
    phase: Literal["initial_brief", "task_plan", "review", "report_task"] | None = Field(
        None,
        description="由代码端 _stamp_decisions 强制覆盖，LLM 无需填写",
    )
    decision_type: str = Field(
        description=(
            "决策类型，自由字符串。建议从以下值中选取以保持一致性："
            "competitor_selection（竞品列表选取）/ "
            "product_type_inference（产品赛道判定）/ "
            "dimension_priority（维度优先级）/ "
            "task_allocation（任务分派）/ "
            "analysis_focus（报告分析重点维度 / 是否需 SWOT）/ "
            "report_structure（报告章节组织）/ "
            "audience_choice（读者类型）/ "
            "other（未归类）"
        )
    )
    chosen: dict = Field(description="最终选择，结构因 decision_type 而异")
    alternatives_considered: list[DecisionAlternative] = Field(
        default_factory=list,
        description="考虑过但拒绝的备选项；为空表示没有显式备选",
    )
    rationale: str = Field(description="为什么这么决定，一段话讲清逻辑，必填")
    inputs_used: list[str] = Field(
        default_factory=list,
        description=(
            "决策依据的 state 字段路径，便于 Q&A 回读原始上下文。"
            "格式：点路径，如 'exploration_result.competitor_names' / "
            "'profiles.飞书.dimensions[0].facts'"
        ),
    )
    ts: str = Field(
        default_factory=_now_iso,
        description="ISO 8601 时间戳，未填则用当前时刻",
    )


# 用户文档蒸馏产物 (D-032 修订版)
# 由 PM phase 1 多模态消化用户上传文档时产出；下游 Collector / Insight / Reporter 共享。


class DomainSeed(BaseModel):
    """用户上传文档蒸馏出的领域 hint，供下游 agent 在做 dimension / competitor 选择时参考。

    生产者：PM `initial_brief_node`（D-032 修订后由 PM 直接消化文档，不再走独立节点）。
    消费者：Collector exploration_node（优先采用 dimension_candidates 而非凭空联网发现）、
            PM TaskPlan / ReportTask（结合 exploration_result 决策）。

    state 控制在 ~2KB，不存原文 —— `source_files` 留 lazy 重读通道。
    """

    source_files: list[str] = Field(
        description="PM 消化的文件路径（绝对或相对项目根），给后续 agent lazy 重读用。代码端覆盖，LLM 不填",
    )
    dimension_candidates: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="用户文档中提到的对比维度候选，如『视频会议人数』『AI 助手』",
    )
    competitor_mentions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="用户文档中提到的竞品名，未联网验证，仅作 hint",
    )
    product_type_hint: str | None = Field(
        None,
        description="一句话产品赛道判断，从文档语境推断",
    )
    terminology: dict[str, str] = Field(
        default_factory=dict,
        description="领域术语表，key=术语 value=简短解释；≤ 30 条",
    )
    extracted_at: str = Field(default_factory=_now_iso)


# PM 4 阶段节点的联合输出：task 主体 + 该阶段产生的若干 DecisionRecord。
# 用 with_structured_output(*Output) 一次 LLM 调用同时拿到任务和决策档案，
# 避免双倍 token 成本。decision_records min_length=1 强制 LLM 至少落一条决策。


class InitialBriefOutput(BaseModel):
    """阶段一联合输出：InitialBrief + 决策档案 + （可选）用户文档蒸馏 DomainSeed。

    D-032 修订版：PM phase 1 多模态消化用户上传文档，同次 LLM 调用产出全部三块。
    domain_seed 仅在用户上传文件时填，否则为 None。
    """

    initial_brief: InitialBrief
    decision_records: list[DecisionRecord] = Field(min_length=1)
    domain_seed: DomainSeed | None = Field(
        None,
        description="若 prompt 含 uploaded_file 内容则填，否则 None；source_files 字段由代码端覆盖",
    )


class TaskPlanOutput(BaseModel):
    """阶段二联合输出：TaskPlan + 决策档案。"""

    task_plan: TaskPlan
    decision_records: list[DecisionRecord] = Field(min_length=1)


class ReportTaskOutput(BaseModel):
    """阶段三联合输出：ReportTask + 决策档案。"""

    report_task: ReportTask
    decision_records: list[DecisionRecord] = Field(min_length=1)


class ReviewOutput(BaseModel):
    """阶段 2.5 PM 评审联合输出：本轮全部 ReviewUnit + 决策档案。

    LLM 一次性产出所有 (agent, product) 对的评审结论，不分次调用。
    review_units 顺序无要求；代码层按 (agent, product_name) 索引。
    """

    review_units: list[ReviewUnit] = Field(min_length=1)
    decision_records: list[DecisionRecord] = Field(min_length=1)


# debate 应用于 2 个 checkpoint：
#    1. pm_taskplan：下游对 PM 阶段二 TaskPlan 的主观挑战（竞品列表 / 产品赛道 / 维度优先级）
#    2. report：Reporter 对 PM 阶段三 ReportTask 的挑战，或 call_report_reviewer skill 终审


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

    target: Literal["pm_taskplan", "report", "pm_initial_brief"] = Field(description="被审对象类型")
    rounds: list[DebateRound]
    final_verdict: Literal["accepted", "rejected", "accepted_with_revision"]
    judge_family: AgentFamily | None = Field(
        description="仲裁方家族，应异于两个辩方。未触发仲裁时为 None",
    )
    judge_rationale: str
    revised_output: dict | None = Field(
        None,
        description="若 verdict 是 accepted_with_revision，给出修订版内容",
    )


# Collector/Insight/Reporter 主动向 PM 表达需求或挑战


class ChallengePayload(BaseModel):
    """
    AgentSignal.payload 的结构化载荷。事实性信号和主观信号共用同一形态：
    - 事实性信号（reroute 路径）：claim 描述问题，evidence 列已观测的数据/URL
    - 主观信号（debate 路径）：claim 为挑战方的核心主张，evidence 为支撑材料

    强约束 evidence 至少 1 条，避免出现"零证据挑战"的空壳调用。
    """

    claim: str = Field(description="挑战或问题的核心陈述")
    evidence: list[str] = Field(
        min_length=1,
        description="支撑 claim 的事实/观测/数据点，至少 1 条",
    )
    observed_data: dict = Field(
        default_factory=dict,
        description="挑战方观测到的额外结构化数据，因 kind 而异，可为空",
    )
    suggested_fix: str | None = Field(
        None,
        description="可选：建议的修订方向",
    )


class AgentSignal(BaseModel):
    """
    Agent 反向通道信号。
    事实性信号（kind=data_gap）走 reroute skill；
    主观判断信号（requires_debate=True）触发 PM 启动 debate。

    signal_id 用于 PM 的消费去重：handle_signal_node 处理后会把 signal_id 写入
    state.consumed_signal_ids，下次扫描时跳过；信号本体保留在 agent_signals 里
    供回溯审计。
    """

    signal_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="信号唯一标识，PM 消费去重用；默认自动生成 UUID",
    )
    from_agent: Literal["collector", "insight", "report"]
    kind: Literal["data_gap", "pm_challenge", "insight_lead", "other"]
    target: str = Field(description="信号所指的 task_id 或 agent 名")
    payload: ChallengePayload = Field(description="结构化挑战/问题载荷")
    requires_debate: bool = Field(
        False,
        description="主观判断时 True，触发跨家族 debate；事实性信号 False",
    )
    reroute_phase: Literal["phase_1", "phase_2", "phase_3"] | None = Field(
        None,
        description=(
            "非空时跳过 reroute LLM 诊断，直接回溯该阶段。"
            "review_node 预检产的 data_gap 已知根因恒为 phase_2，无需再让 LLM 判一遍。"
        ),
    )
    ts: str = Field(description="ISO 8601 时间戳")
