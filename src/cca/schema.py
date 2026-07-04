"""
Competitive analysis system data models.
Generic skeleton -- no hardcoded industry fields; dimensions are discovered by
agents at runtime; every conclusion must be tied to evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _now_iso() -> str:
    """Current ISO 8601 UTC timestamp, for default_factory."""
    return datetime.now(UTC).isoformat()

# the three model families, used to constrain debate typing
AgentFamily = Literal["gpt-5", "deepseek", "doubao"]


class Evidence(BaseModel):
    """A single piece of evidence: source URL + the original snippet backing the claim."""

    source_url: str
    snippet: str | None = Field(None, description="Original excerpt from the source page backing this claim")
    fetched_at: str = Field(
        default_factory=_now_iso,
        description="ISO 8601 timestamp, defaults to the current time",
    )


class Fact(BaseModel):
    """A verifiable objective statement; must be backed by at least one piece of evidence."""

    statement: str = Field(description="An objective statement with no subjective judgment, e.g. 'Feishu video calls support up to 300 participants'")
    evidence: list[Evidence] = Field(min_length=1)


class Dimension(BaseModel):
    """
    A single analysis dimension, distilled by domain_seed_node (from a user-uploaded
    doc) or discovered online by Collector.
    category is an open string, typical values: 'features' / 'pricing' / 'user
    sentiment' / 'ecosystem' / 'market position' / 'tech architecture'.
    """

    name: str = Field(description="Dimension name, e.g. 'max video call participants', 'mobile offline support'")
    category: str = ""  # relaxed during collection: open classification the model often misses; a missing value shouldn't kill the whole dimension
    facts: list[Fact] = Field(default_factory=list)
    cross_product_note: str | None = Field(
        None,
        description="A factual cross-product comparison conclusion, must be derived from the data in facts, no subjective judgment",
    )


class PricingTier(BaseModel):
    """A single pricing tier, sourced from the official site or a public pricing page.

    Relaxed during collection: tiers with no price number are allowed too (the report
    stage decides whether to include them in cost comparisons).
    """

    name: str
    price_per_user_monthly: float | None = None
    price_per_user_yearly: float | None = None
    currency: str | None = Field(None, description="ISO 4217 currency code, e.g. 'CNY', 'USD', 'EUR'")
    user_limit: int | None = Field(None, description="None means unlimited users")
    included_features: list[str] = Field(default_factory=list)
    source: Evidence | None = None


class PricingInfo(BaseModel):
    """A product's full pricing structure. Relaxed during collection: has_free_tier
    can be omitted, invalid pricing_model falls back to unknown."""

    has_free_tier: bool | None = None
    pricing_model: Literal["per_user", "per_team", "custom", "unknown"] = "unknown"
    tiers: list[PricingTier] = Field(default_factory=list)

    @field_validator("pricing_model", mode="before")
    @classmethod
    def _coerce_unknown_model(cls, v: object) -> object:
        """The model often returns values outside the enum; normalize to unknown so
        one bad field doesn't ruin the whole pricing block."""
        return v if v in {"per_user", "per_team", "custom", "unknown"} else "unknown"


class ReviewSample(BaseModel):
    """The raw text of a single user review."""

    text: str
    rating: int | None = Field(None, ge=1, le=5)
    platform: str = Field(
        default="other",
        description=(
            "The review's source platform, an open string with no assumed product "
            "domain. Apps: 'appstore_cn'/'appstore_us'; social: 'zhihu'/'weibo'; "
            "e-commerce: 'tmall'/'jd'/'amazon'; a niche/specialist review site or any "
            "custom source name; use 'other' if unknown"
        ),
    )
    source: Evidence | None = None


class UserSentiment(BaseModel):
    """Aggregated user sentiment; all data must come from objective scraping of public channels."""

    aggregate_rating: float | None = Field(
        None, ge=1, le=5,
        description="Channel-aggregated rating, normalized to 1-5 (App Store rating / e-commerce stars / niche-site rating all fit)",
    )
    rating_review_count: int | None = Field(None, description="Sample size (review/rating count) behind the rating")
    rating_source: str | None = Field(
        None,
        description="The rating's source channel, an open string, e.g. 'appstore_cn' / 'tmall' / 'jd' / 'amazon' / 'fragrantica'",
    )
    positive_themes: list[str] = Field(
        default_factory=list,
        description="Themes distilled from positive reviews, judged and summarized directly by the LLM",
    )
    negative_themes: list[str] = Field(
        default_factory=list,
        description="Themes distilled from negative reviews (complaints), judged and summarized directly by the LLM",
    )
    representative_reviews: list[ReviewSample] = Field(default_factory=list)
    sources: list[Evidence] = Field(default_factory=list)


class SWOTPoint(BaseModel):
    """A single SWOT point; must reference the fact statements that support it."""

    point: str
    supporting_fact_statements: list[str] = Field(
        min_length=1,
        description="Quotes the original statement text from Dimension.facts, to keep it traceable",
    )


class SWOT(BaseModel):
    """The four SWOT quadrants; each is a list of SWOTPoint."""

    strengths: list[SWOTPoint]
    weaknesses: list[SWOTPoint]
    opportunities: list[SWOTPoint]
    threats: list[SWOTPoint]


class ProductProfile(BaseModel):
    """
    A single product's competitive-analysis profile, generic across any product domain.
    Fill order:
        1. PM drafts: product_name required; company is an optional hint
        2. Collector verifies online + fills in: product_type / target_users /
           dimensions / pricing / sources / website (may challenge PM's hint via debate)
        3. Insight fills: sentiment
        4. PM's debate-review fills: qa_flags / data_confidence

    SWOT is no longer an owned profile field -- Reporter produces it via a tool at
    report time and writes it straight into the MD, never back into state.profiles.
    """

    # drafted by PM Agent (from training knowledge; company is a hint Collector may challenge)
    product_name: str
    company: str | None = Field(None, description="A seed from PM's training knowledge, verified online by Collector")

    # verified and filled in online by Collector Agent
    product_type: str | None = Field(None, description="Inferred online by Collector, converged via PM debate")
    target_users: str | None = Field(None, description="Target users, taken verbatim from the official site")
    website: str | None = Field(None, description="Official site URL, found online by Collector")
    dimensions: list[Dimension] = Field(default_factory=list)
    pricing: PricingInfo | None = None
    sources: list[Evidence] = Field(default_factory=list)

    # filled by Insight Agent
    sentiment: UserSentiment | None = None
    key_events: list[Fact] = Field(
        default_factory=list,
        description="Material events and business conflicts/interest disputes -- objective statement + evidence; causal interpretation is left to Report",
    )

    # filled by PM's debate-review
    qa_flags: list[str] = Field(
        default_factory=list,
        description="Description of a failed check, e.g. 'pricing info inconsistent with raw data'",
    )
    data_confidence: float | None = Field(
        None,
        ge=0,
        le=1,
        description="PM's overall data-confidence rating",
    )


class QAResult(BaseModel):
    """QA Agent's verdict on a single product profile."""

    product_name: str
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    note: str | None = None


# PM's first-round brief handed to Collector, guiding its web exploration; Collector may accept or challenge it
class InitialBrief(BaseModel):
    """
    PM's first-draft analysis brief after receiving user input, guiding Collector's
    first-round output.
    """

    target_product: str
    company_hint: str | None = Field(
        None, description="A company seed from PM's training knowledge; Collector may challenge it"
    )
    user_query: str = Field(description="The raw user input, for Collector to understand intent")


class ProductBrief(BaseModel):
    """The minimal competitor profile produced by Collector's first-round rough exploration."""

    product_name: str
    company: str | None = None
    website: str | None = None
    product_type: str | None = None


class CollectorExplorationResult(BaseModel):
    """
    Output of Collector's first ReAct round of web exploration.
    Written back to state after converging via PM debate, feeding PM phase 2's TaskPlan.
    """

    target_product: str
    product_type: str = Field(description="Product category inferred online by Collector")
    competitor_names: list[str] = Field(description="Main competitors discovered online by Collector")
    discovered_dimensions: list[str] = Field(description="Comparison dimension candidates summarized online by Collector")
    initial_profiles: list[ProductBrief] = Field(
        description="First-round output, including product_name, company, website, product_type"
    )
    rationale: str | None = None


# PM's second-round task refinement handed to Collector/Insight, guiding the next round's output; they may accept or challenge it
class CollectTask(BaseModel):
    """A single collection task PM assigns to Collector."""

    product_name: str
    priority_dimensions: list[str] = Field(
        default_factory=list,
        description="Priority dimensions PM determined from product type and DomainPack; empty means Collector decides on its own",
    )
    allow_self_extension: bool = Field(
        True,
        description="Whether Collector may add its own extra searches/fetches",
    )


class InsightTask(BaseModel):
    """A single analysis task PM assigns to Insight."""

    product_name: str
    target_platforms: list[str] = Field(
        default_factory=list,
        description=(
            "A data-source hint from PM, an open string (App Store / e-commerce / "
            "niche community / any source name), no assumed product domain; Insight "
            "may reject/extend/replace it; empty means Insight decides on its own"
        ),
    )
    priority_dimensions: list[str] = Field(
        default_factory=list,
        description="Priority dimensions PM determined from product type and DomainPack; empty means Insight decides on its own",
    )
    allow_self_extension: bool = Field(
        True,
        description="Whether Insight may add its own extra platforms/themes",
    )


class TaskPlan(BaseModel):
    """
    PM phase 2: the fine-grained task package handed to Collector and Insight,
    built from CollectorExplorationResult.
    """

    target_product: str
    product_type: str = Field(description="Authoritative product type after this round's debate converges")
    competitor_names: list[str] = Field(description="Authoritative competitor list after this round's debate converges")
    collect_tasks: list[CollectTask]
    insight_tasks: list[InsightTask]
    tentative_buckets: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "PM's preset list of canonical buckets (<=8), a soft guide for Collector/"
            "Insight during collection, and reused as a preference by Reporter's "
            "dimension_canonical_map semantic alignment step. Not enforced: dimension "
            "alignment is Reporter's semantic-merge job, so collection isn't held "
            "hostage to bucket naming."
        ),
    )


# PM's third-round analysis + writing task handed to Report. The old AnalystTask
# fields (focus_dimensions / require_swot / cross_product_comparison_required) have
# been merged in here -- Reporter's ReAct loop now handles ranking, SWOT analysis,
# and writing the body all at once.
class ReportTask(BaseModel):
    """PM phase 3: the analysis + report task handed down once Collector+Insight pass QA."""

    target_product: str = Field(description="The product being analyzed")
    competitors: list[str] = Field(description="List of competitor names")
    product_names: list[str] = Field(
        default_factory=list,
        description=(
            "Product names included in the comparison, usually = [target_product] + "
            "competitors. Used by the dimension_ranking / SWOT tools to determine "
            "coverage; if empty, Reporter infers it"
        ),
    )
    focus_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Dimensions PM wants highlighted. Reporter uses this to decide which "
            "dimensions submit_dimension_ranking covers; if empty, Reporter decides on its own"
        ),
    )
    require_swot: bool = Field(
        True,
        description="Whether Reporter must call finalize_swot to produce the SWOT section",
    )
    cross_product_comparison_required: bool = Field(
        True,
        description="Whether a cross-product comparison section is required",
    )
    output_formats: list[Literal["markdown", "pdf"]] = Field(
        default_factory=lambda: ["markdown", "pdf"],
    )
    target_audience: str | None = Field(
        None,
        description="Reader type, e.g. 'product lead', 'technical reviewer' -- affects Reporter's tone",
    )
    sections: list[str] = Field(
        default_factory=list,
        description="Sections the report should include; if empty, Reporter organizes it on its own",
    )
    invoke_call_report_reviewer: bool = Field(
        True,
        description="Whether to call the call_report_reviewer skill (Doubao final review); on by default, always runs exactly once",
    )
    dimension_canonical_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps profiles[*].dimensions[*].name -> canonical bucket. Produced by PM "
            "phase 3 from the actually-collected dim names; the code layer enforces "
            "100% coverage, auto-assigning any gaps to the fallback bucket. Reporter "
            "ranks by bucket using this map."
        ),
    )


# Review result: PM's verdict on Collector/Insight output, including rework
# suggestions and QA results; used for PM's own record-keeping and later analysis,
# and can be queried by users to understand PM's review logic
ReviewStatus = Literal["passed", "needs_retry", "forced"]


class ReviewUnit(BaseModel):
    """
    PM's review verdict on one (agent, product) round's output.
    PM reviews once Collector+Insight finish a parallel round; needs_retry triggers
    rework, after which PM reviews again and appends a new ReviewUnit; retry_count > 2
    is marked forced.
    """

    agent: Literal["collector", "insight"]
    product_name: str
    status: ReviewStatus
    retry_count: int = Field(description="How many reworks this (agent, product) had before this review")
    qa_flags: list[str] = Field(
        default_factory=list,
        description="Description of a failed check, e.g. 'pricing info inconsistent with raw data'",
    )
    pm_note: str | None = None
    reviewed_at: str | None = Field(None, description="ISO 8601 timestamp")


class HumanReviewFeedback(BaseModel):
    """The user's one-shot free-text revision feedback on Collector/Insight output at phase 2.5.

    The frontend offers a single text box (to keep cognitive load low) with no
    pre-classification -- splitting it out (which parts target collection, which
    target sentiment analysis, which are competitor add/remove requests) is left to
    PM to parse during review/re-routing.
    """

    raw_feedback: str | None = Field(None, description="The user's raw revision text, unclassified")
    approved: bool = Field(False, description="True = no revisions, pass straight through")

    def has_revisions(self) -> bool:
        """Whether there's a substantive revision for PM to adopt (approved passing
        through doesn't count)."""
        return not self.approved and bool(self.raw_feedback and self.raw_feedback.strip())


# Decision record: whenever PM produces a task at each phase, it also persists "why
# this decision was made", backing offline Q&A (user asks "why these competitors?")
# and debate defense (PM reads its own rationale back when defending)


class DecisionAlternative(BaseModel):
    """An option that was considered but rejected."""

    option: str = Field(description="The alternative, e.g. 'Tencent Meeting', 'plan A ranked by dimension priority'")
    rejected_reason: str = Field(description="Why it wasn't chosen, one sentence of clear reasoning")


class DecisionRecord(BaseModel):
    """
    A single PM decision record. One phase usually has several DecisionRecords (e.g.
    task_plan simultaneously decides the competitor list / dimension priority / task
    allocation -- these should be 3 separate records, not crammed into one).
    """

    decision_id: str = Field(
        default_factory=lambda: f"D-{uuid4().hex[:8]}",
        description="Unique decision id, citable from report sections (e.g. footnote [D-a1b2c3d4])",
    )
    phase: Literal["initial_brief", "task_plan", "review", "report_task"] | None = Field(
        None,
        description="Force-overwritten by the code layer's _stamp_decisions; the LLM doesn't need to fill it",
    )
    decision_type: str = Field(
        description=(
            "Decision type, a free string. Prefer picking from these for consistency: "
            "competitor_selection / product_type_inference / dimension_priority / "
            "task_allocation / analysis_focus (report's analysis focus dimensions / "
            "whether SWOT is needed) / report_structure (report section organization) / "
            "audience_choice / other (uncategorized)"
        )
    )
    chosen: dict = Field(description="The final choice; its structure varies by decision_type")
    alternatives_considered: list[DecisionAlternative] = Field(
        default_factory=list,
        description="Alternatives considered but rejected; empty means no explicit alternatives",
    )
    rationale: str = Field(description="Why this was decided, one paragraph of clear reasoning, required")
    inputs_used: list[str] = Field(
        default_factory=list,
        description=(
            "State field paths this decision drew on, for Q&A to read back the "
            "original context. Format: dotted path, e.g. "
            "'exploration_result.competitor_names' / 'profiles.Feishu.dimensions[0].facts'"
        ),
    )
    ts: str = Field(
        default_factory=_now_iso,
        description="ISO 8601 timestamp, defaults to the current time if omitted",
    )


# Distillate of a user-uploaded doc (D-032 revision)
# Produced when PM phase 1 digests a user-uploaded doc multimodally; shared by
# downstream Collector / Insight / Reporter.


class DomainSeed(BaseModel):
    """A domain hint distilled from a user-uploaded doc, for downstream agents to
    reference when choosing dimensions/competitors.

    Producer: PM's `initial_brief_node` (after the D-032 revision, PM digests the
    doc directly, no separate node).
    Consumers: Collector's exploration_node (prefers dimension_candidates over
    discovering from scratch online), PM's TaskPlan / ReportTask (decides using it
    alongside exploration_result).

    Kept to ~2KB in state, doesn't store the raw text -- `source_files` is the lazy
    re-read channel.
    """

    source_files: list[str] = Field(
        description="File paths PM digested (absolute or relative to project root), for downstream agents to lazily re-read. Overwritten by the code layer, not filled by the LLM",
    )
    dimension_candidates: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Comparison-dimension candidates mentioned in the user's doc, e.g. 'video call participant limit', 'AI assistant'",
    )
    competitor_mentions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Competitor names mentioned in the user's doc, unverified online, just a hint",
    )
    product_type_hint: str | None = Field(
        None,
        description="A one-sentence product-category judgment, inferred from the doc's context",
    )
    terminology: dict[str, str] = Field(
        default_factory=dict,
        description="Domain glossary, key=term value=short explanation; <=30 entries",
    )
    extracted_at: str = Field(default_factory=_now_iso)


# Combined output of PM's 4 phase nodes: the task body + the DecisionRecords produced
# in that phase. Using with_structured_output(*Output), one LLM call returns both the
# task and the decision records, avoiding double the token cost. decision_records'
# min_length=1 forces the LLM to log at least one decision.


class InitialBriefOutput(BaseModel):
    """Phase-1 combined output: InitialBrief + decision records + (optional) DomainSeed
    distilled from the user's doc.

    D-032 revision: PM phase 1 digests a user-uploaded doc multimodally, producing
    all three parts in the same LLM call. domain_seed is only filled when the user
    uploaded a file, otherwise None.
    """

    initial_brief: InitialBrief
    decision_records: list[DecisionRecord] = Field(min_length=1)
    domain_seed: DomainSeed | None = Field(
        None,
        description="Filled if the prompt includes uploaded_file content, otherwise None; source_files is overwritten by the code layer",
    )


class TaskPlanOutput(BaseModel):
    """Phase-2 combined output: TaskPlan + decision records."""

    task_plan: TaskPlan
    decision_records: list[DecisionRecord] = Field(min_length=1)


class ReportTaskOutput(BaseModel):
    """Phase-3 combined output: ReportTask + decision records."""

    report_task: ReportTask
    decision_records: list[DecisionRecord] = Field(min_length=1)


class ReviewOutput(BaseModel):
    """Phase-2.5 PM review combined output: this round's full set of ReviewUnits + decision records.

    The LLM produces the verdict for every (agent, product) pair in one shot, not
    called repeatedly. review_units order doesn't matter; the code layer indexes by
    (agent, product_name).
    """

    review_units: list[ReviewUnit] = Field(min_length=1)
    decision_records: list[DecisionRecord] = Field(min_length=1)


# debate applies at 2 checkpoints:
#    1. pm_taskplan: a downstream subjective challenge to PM phase 2's TaskPlan
#       (competitor list / product category / dimension priority)
#    2. report: Reporter's challenge to PM phase 3's ReportTask, or the
#       call_report_reviewer skill's final review


class DebatePosition(BaseModel):
    """One debater's position in a single round of the 4-phase debate."""

    agent_family: AgentFamily
    claim: str = Field(description="The debater's core claim")
    evidence: list[str] = Field(min_length=1, description="Facts/citations backing the claim, at least 1")


class DebateRound(BaseModel):
    """A single debate round: both sides state their position independently -> critique each other -> revise."""

    round: int = Field(description="Round number, starting from 1")
    positions: list[DebatePosition]
    critiques: dict[AgentFamily, str] = Field(
        description="Each debater's critique of the other's position, keyed by the family being critiqued",
    )
    refinements: dict[AgentFamily, str] = Field(
        description="Each debater's revised position after seeing the critique, keyed by the family that revised",
    )


class DebateResult(BaseModel):
    """The full debate result: N rounds + a third-family judge."""

    target: Literal["pm_taskplan", "report", "pm_initial_brief"] = Field(description="Type of the object under review")
    rounds: list[DebateRound]
    final_verdict: Literal["accepted", "rejected", "accepted_with_revision"]
    judge_family: AgentFamily | None = Field(
        description="The judging family, should differ from both debaters. None if judging was never triggered",
    )
    judge_rationale: str
    revised_output: dict | None = Field(
        None,
        description="If verdict is accepted_with_revision, the revised content",
    )


# Collector/Insight/Reporter proactively raising a request or challenge to PM


class ChallengePayload(BaseModel):
    """
    The structured payload of AgentSignal.payload. Factual and subjective signals
    share the same shape:
    - factual signal (reroute path): claim describes the problem, evidence lists observed data/URLs
    - subjective signal (debate path): claim is the challenger's core argument, evidence is supporting material

    evidence is hard-constrained to at least 1 entry, to prevent an "evidence-free challenge" empty call.
    """

    claim: str = Field(description="The core statement of the challenge or problem")
    evidence: list[str] = Field(
        min_length=1,
        description="Facts/observations/data points backing the claim, at least 1",
    )
    observed_data: dict = Field(
        default_factory=dict,
        description="Extra structured data the challenger observed, varies by kind, may be empty",
    )
    suggested_fix: str | None = Field(
        None,
        description="Optional: a suggested direction for the fix",
    )


class AgentSignal(BaseModel):
    """
    An agent's back-channel signal.
    Factual signals (kind=data_gap) go through the reroute skill;
    subjective-judgment signals (requires_debate=True) trigger PM to start a debate.

    signal_id is used for PM's consumption dedup: after handle_signal_node processes
    a signal, its signal_id is written to state.consumed_signal_ids and skipped on
    the next scan; the signal itself stays in agent_signals for audit/replay.
    """

    signal_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique signal id for PM's consumption dedup; auto-generated UUID by default",
    )
    from_agent: Literal["collector", "insight", "report"]
    kind: Literal["data_gap", "pm_challenge", "insight_lead", "other"]
    target: str = Field(description="The task_id or agent name this signal targets")
    payload: ChallengePayload = Field(description="Structured challenge/problem payload")
    requires_debate: bool = Field(
        False,
        description="True for a subjective judgment, triggering cross-family debate; False for a factual signal",
    )
    reroute_phase: Literal["phase_1", "phase_2", "phase_3"] | None = Field(
        None,
        description=(
            "When set, skips the reroute LLM diagnosis and rolls back to this phase "
            "directly. review_node's precheck-produced data_gap always has phase_2 as "
            "its known root cause, so there's no need to make the LLM judge it again."
        ),
    )
    ts: str = Field(description="ISO 8601 timestamp")
