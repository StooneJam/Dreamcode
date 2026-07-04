"""
LangGraph main-graph shared state.
Split from the Pydantic domain models: domain classes live in schema.py, runtime
state lives here.
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


def _is_empty(v: object) -> bool:
    """None / empty container / empty string count as "no value". 0 and False are
    valid values, not empty."""
    return v is None or v == [] or v == {} or v == ""


def _merge_profiles(left: dict[str, dict], right: dict[str, dict]) -> dict[str, dict]:
    """Merge reducer for profiles: on a shared key, right's fields overwrite left's,
    but fields unique to either side are kept.

    Collector writes dimensions/pricing/sources, Insight writes sentiment. Concurrent
    writers each only update their own fields, never dropping fields the other wrote.

    Overwrite rule: a right-hand "empty value" (None / [] / {} / "") never overwrites
    an existing non-empty left value. This guard is the core of fanout concurrency
    safety -- when Collector's real profile and a crashed worker's empty placeholder
    (_skip_result, dimensions=[]/sources=[]) land on the same product key, regardless
    of fold order the placeholder can never blank out real data (the old version only
    guarded against None, not [], and would get overwritten).

    SWOT no longer goes through profile -- Reporter produces it itself and writes
    straight into the report body, never back into state.profiles.
    """
    merged = dict(left)
    for name, profile in right.items():
        if name in merged:
            base = dict(merged[name])
            for k, v in profile.items():
                if not _is_empty(v) or k not in base or _is_empty(base.get(k)):
                    base[k] = v
            merged[name] = base
        else:
            merged[name] = profile
    return merged


class CCAState(TypedDict):
    """Shared workbench between agents.

    profiles is keyed by product_name storing ProductProfile.model_dump();
    review_state / audit_log / qa_notes use the add reducer, so concurrent writes
    from multiple nodes append automatically.
    """
    user_query: str
    target_product: str
    report_language: str  # "zh" | "en", defaults to "zh"

    # path to the user-uploaded doc (written by the CLI/frontend before calling the
    # graph); v1 only takes the first one. PM phase 1 digests it directly.
    user_files: list[str] | None

    # PM phase 1's InitialBrief; Collector's phase-1 ExplorationResult (written back after debate converges)
    initial_brief: dict | None           # InitialBrief.model_dump()
    # domain hint PM phase 1 distilled from the user's doc (only set when user_files
    # is non-empty); shared by downstream Collector / Insight / Analyst
    domain_seed: dict | None             # DomainSeed.model_dump()
    exploration_result: dict | None      # CollectorExplorationResult.model_dump()

    # tasks PM phases 2-3 hand down
    competitor_names: list[str]
    task_plan: dict | None               # TaskPlan.model_dump() - filled by PM phase 2
    report_task: dict | None             # ReportTask.model_dump() - filled by PM phase 3

    # per-product profiles (filled progressively by Collector / Insight / PM)
    # _merge_profiles reducer: concurrent writers each only overwrite their own
    # fields, never clearing fields other agents already wrote
    profiles: Annotated[dict[str, dict], _merge_profiles]

    # PM's review ledger, accumulating each round's review output
    # status=forced entries are the data source for the report's "not fully reviewed" section
    review_state: Annotated[list[dict], add]   # list[ReviewUnit.model_dump()]

    # cumulative reroute count. review_node raises needs_retry -> handle_signal
    # reroutes successfully -> +1. At 2, review_node escalates all needs_retry to
    # forced and stops raising signals, to prevent an infinite loop.
    reroute_count: int

    # phase 2.5 human-in-the-loop: the user's one-shot free-text revision feedback on Collector/Insight output
    human_review_feedback: dict | None        # HumanReviewFeedback.model_dump()
    human_review_done: bool                   # gate interrupt: pauses to collect feedback only once
    human_feedback_consumed: bool             # gate review adoption: feedback only factors into one review round

    # final report review output (from call_report_reviewer's cross-family debate)
    qa_results: list[dict]
    report_status: Literal["pending", "passed", "failed", "unreviewed"]
    report_md: str | None
    report_pdf_path: str | None

    # analysis timing (ISO 8601 UTC)
    analysis_start_ts: str | None   # recorded when the graph starts
    analysis_end_ts: str | None     # recorded when the report finishes

    # logs and signals accumulated across phases
    qa_notes: Annotated[list[str], add]
    audit_log: Annotated[list[dict], add]
    debate_results: Annotated[list[dict], add]   # accumulated DebateResult.model_dump()
    agent_signals: Annotated[list[dict], add]    # accumulated AgentSignal.model_dump() (never deleted, for audit/replay)
    consumed_signal_ids: Annotated[list[str], add]  # signal_ids PM has already handled, a dedup pointer
    decision_log: Annotated[list[dict], add]     # accumulated DecisionRecord.model_dump(), backs offline Q&A and debate defense
