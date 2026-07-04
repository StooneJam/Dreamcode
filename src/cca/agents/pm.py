"""PM Agent -- three-phase planning + signal dispatch, pure structured LLM calls, no ReAct tools.

Phase nodes: initial_brief / task_plan / report_task. Downstream signals all
funnel into handle_signal_node.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import ValidationError

from cca.agents._streaming import emit_sse
from cca.llm.factory import cross_family_enabled, get_llm
from cca.schema import (
    AgentFamily,
    AgentSignal,
    ChallengePayload,
    DebatePosition,
    DebateResult,
    DecisionRecord,
    HumanReviewFeedback,
    InitialBriefOutput,
    ReportTask,
    ReportTaskOutput,
    ReviewOutput,
    ReviewUnit,
    TaskPlanOutput,
)
from cca.skills.debate import DebateTarget, run_debate
from cca.skills.reroute import apply_reroute, apply_reroute_phase, reroute
from cca.state import CCAState
from cca.tools.pdf_reader import UnsupportedFormat, read_file

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "pm.md"

PM_FAMILY: AgentFamily = "gpt-5"
CHALLENGER_FAMILY: AgentFamily = "deepseek"

# signal.target -> debate target
_TARGET_TO_DEBATE = {
    "initial_brief": "pm_initial_brief",
    "task_plan": "pm_taskplan",
    "report_task": "report",
}
# debate target -> corresponding state task field
_DEBATE_TARGET_TO_TASK_FIELD = {
    "pm_initial_brief": "initial_brief",
    "pm_taskplan": "task_plan",
    "report": "report_task",
}

# truncate a single uploaded doc so the prompt doesn't blow up
_MAX_FILE_CHARS = 50_000

PMPhase = Literal["initial_brief", "task_plan", "review", "report_task"]

# review_node config
_REROUTE_HARD_LIMIT = 2          # once state.reroute_count hits this, needs_retry -> forced
_PER_UNIT_RETRY_LIMIT = 2        # once a single (agent, product)'s retry count hits this, needs_retry -> forced
_SENTIMENT_MIN_REVIEWS = 1       # min review sample for Insight sentiment (1 is enough; below this, flagged forced)
_REVIEW_INVOKE_ATTEMPTS = 2      # review has a code-layer fallback, so don't over-retry the LLM: 1 + 1 retry, then degrade


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _phase_prefix(phase: str) -> str:
    return f"## 当前阶段：{phase}\n\n"


def _stamp_decisions(records: list[DecisionRecord], phase: PMPhase) -> list[dict]:
    """Force-overwrite the phase field before persisting, in case the LLM reports it wrong."""
    out = []
    for r in records:
        d = r.model_dump()
        d["phase"] = phase
        out.append(d)
    return out


def _load_user_file(state: CCAState) -> tuple[str | None, str | None, list[dict]]:
    """Read the first file in state.user_files -> (path, text, audit). Multi-file / failure
    only logs to audit, never raises."""
    files = state.get("user_files") or []
    if not files:
        return None, None, []

    audit: list[dict] = []
    if len(files) > 1:
        audit.append({
            "agent": "pm", "event": "multi_file_warning",
            "got": files, "kept": files[0],
        })

    path = files[0]
    try:
        text = read_file(path)
    except (FileNotFoundError, UnsupportedFormat) as e:
        audit.append({"agent": "pm", "event": "file_read_failed", "path": path, "error": str(e)})
        return None, None, audit

    if len(text) > _MAX_FILE_CHARS:
        audit.append({
            "agent": "pm", "event": "file_truncated", "path": path,
            "original_chars": len(text), "kept_chars": _MAX_FILE_CHARS,
        })
        text = text[:_MAX_FILE_CHARS]
    audit.append({"agent": "pm", "event": "file_read_ok", "path": path, "chars": len(text)})
    return path, text, audit


_PM_INVOKE_MAX_RETRIES = int(os.getenv("PM_INVOKE_MAX_RETRIES", "4"))


def _extract_json_block(text: str) -> str:
    """Pull a JSON object out of free text: first { to last }."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _invoke_structured(
    output_type, phase_label: str, base_messages: list, attempts: int,
) -> tuple[object | None, str | None]:
    """function_calling self-repair loop. Returns (structured result, last error);
    returns (None, last error) once attempts are exhausted.

    ValidationError -- LLM omitted a required field: feed the error back for it to fix.
    Returns None -- LLM didn't emit a function_call (Doubao/Ark occasionally ignores a
        forced tool_choice): re-emphasize the function call is mandatory.
    OutputParserException -- Doubao names the tool after the nested type (e.g. InitialBrief
        instead of InitialBriefOutput) and the parser can't find it. Retrying hits the same
        wall, so bail out of the structured channel straight to the JSON fallback.
    """
    llm = get_llm(PM_FAMILY).with_structured_output(output_type, method="function_calling")
    last_error: str | None = None
    for attempt in range(attempts):
        messages = base_messages if last_error is None else base_messages + [HumanMessage(content=last_error)]
        try:
            result = llm.invoke(messages)
        except OutputParserException as e:
            print(f"  [pm:{phase_label}] WARN: tool name 不匹配（{e}），转 JSON 直出兜底", flush=True)
            return None, str(e)
        except ValidationError as e:
            last_error = (
                f"上一次输出有 schema 错误，请严格按 {output_type.__name__} schema 重新输出。\n"
                f"错误详情：\n{e}\n\n"
                f"特别注意：DecisionRecord.rationale 是必填字符串，每条都必须有。"
            )
            print(f"  [pm:{phase_label}] WARN: ValidationError on attempt {attempt + 1}, retrying", flush=True)
            continue
        if result is None:
            last_error = (
                f"上一次回复没有调用 function（第 {attempt + 1} 次）。"
                f"你必须通过 function_call 返回严格符合 {output_type.__name__} schema 的结构化对象，"
                f"禁止用自由文本回答。直接调用工具函数，不要输出任何解释文字。"
            )
            print(f"  [pm:{phase_label}] WARN: LLM 返 None（attempt {attempt + 1}/{attempts}），retry", flush=True)
            continue
        return result, None
    return None, last_error


def _invoke_json_fallback(output_type, base_messages: list):
    """Fallback once the structured channel is exhausted: have the model emit raw JSON,
    validated locally with pydantic.

    Bypasses the tool_call channel -- when Doubao/Ark occasionally ignores a forced
    tool_choice and answers in free text, function_calling always returns None, so
    retrying there is pointless. The result is still the LLM's real output, not a stub.
    """
    schema = json.dumps(output_type.model_json_schema(), ensure_ascii=False)
    instruction = HumanMessage(content=(
        f"直接输出一个严格符合下面 JSON Schema 的 JSON 对象，"
        f"不要解释、不要 markdown 围栏：\n{schema}"
    ))
    raw = get_llm(PM_FAMILY).invoke(base_messages + [instruction])
    content = raw.content if isinstance(raw.content, str) else str(raw.content)
    try:
        return output_type.model_validate_json(_extract_json_block(content))
    except (ValidationError, ValueError):
        print(f"  [pm] JSON 直出失败，豆包原始返回（前 1000 字）：\n{content[:1000]}", flush=True)
        raise


def _invoke_pm(output_type, phase_label: str, payload: dict, *, max_attempts: int | None = None):
    """Unified PM call: function_calling self-repair, then JSON fallback, then raise.

    max_attempts caps total function_calling tries (including the first). Defaults to
    _PM_INVOKE_MAX_RETRIES; nodes with a code-layer fallback (review) pass a small value
    to fail fast instead of grinding. Not cached, to keep judgment flexible.
    """
    attempts = max_attempts or _PM_INVOKE_MAX_RETRIES
    base_messages = [
        SystemMessage(content=_load_system_prompt()),
        HumanMessage(content=_phase_prefix(phase_label) + json.dumps(payload, ensure_ascii=False)),
    ]

    result, last_error = _invoke_structured(output_type, phase_label, base_messages, attempts)
    if result is not None:
        return result

    print(f"  [pm:{phase_label}] 结构化通道耗尽，切 JSON 直出通道兜底", flush=True)
    try:
        return _invoke_json_fallback(output_type, base_messages)
    except (ValidationError, ValueError) as e:
        raise RuntimeError(
            f"PM {phase_label} 节点 function_calling + JSON 直出均失败。"
            f"function_calling 错误：{last_error}；JSON 直出错误：{e}。"
            f"检查 model id 的 function_calling 支持或 prompt 是否过长。"
        ) from e


def initial_brief_node(state: CCAState) -> dict:
    """Phase 1: digest user_query + optional doc, producing InitialBrief + decision
    records + optional DomainSeed."""
    file_path, file_text, file_audit = _load_user_file(state)
    payload: dict = {"user_query": state["user_query"]}
    if file_text is not None:
        payload["uploaded_file"] = {"path": file_path, "content": file_text}

    result = cast(InitialBriefOutput, _invoke_pm(
        InitialBriefOutput, "阶段一 InitialBrief", payload,
    ))

    updates: dict = {
        "initial_brief": result.initial_brief.model_dump(),
        # write back the refined target_product as the single source of truth after phase 1:
        # downstream (Collector exploration / report / frontend summary) all read
        # state.target_product, avoiding a split where PM refined the target but the report
        # still reads the raw entry value. The original user input stays in state.user_query.
        "target_product": result.initial_brief.target_product,
        "decision_log": _stamp_decisions(result.decision_records, "initial_brief"),
    }
    if result.domain_seed is not None and file_path is not None:
        ds = result.domain_seed.model_dump()
        ds["source_files"] = [file_path]  # force-overwritten at the code layer
        updates["domain_seed"] = ds
        emit_sse({"type": "domain_seed",
                  "product_type_hint": ds.get("product_type_hint"),
                  "dimension_candidates": ds.get("dimension_candidates", []),
                  "competitor_mentions": ds.get("competitor_mentions", []),
                  "terminology": ds.get("terminology", {})})
    if file_audit:
        updates["audit_log"] = file_audit
    emit_sse({"type": "progress", "pct": 8, "sec_left": 120})
    return updates


def _human_feedback_text(state: CCAState) -> str | None:
    """state.human_review_feedback -> raw text if it has substantive revisions, else None."""
    raw = state.get("human_review_feedback")
    if not raw:
        return None
    fb = HumanReviewFeedback(**raw)
    return fb.raw_feedback if fb.has_revisions() else None


def task_plan_node(state: CCAState) -> dict:
    """Phase 2: build TaskPlan + decision records from exploration_result.

    If state.human_review_feedback carries user revisions (a feedback-driven reroute),
    inject the raw text into the payload so PM can parse it and adjust collect/insight tasks.
    """
    payload: dict = {
        "user_query": state["user_query"],
        "exploration_result": state.get("exploration_result", {}),
        "competitor_names": state.get("competitor_names", []),
    }
    if feedback := _human_feedback_text(state):
        payload["human_review_feedback"] = feedback

    result = cast(TaskPlanOutput, _invoke_pm(
        TaskPlanOutput, "阶段二 TaskPlan", payload,
    ))
    emit_sse({"type": "progress", "pct": 22, "sec_left": 95})
    return {
        "task_plan": result.task_plan.model_dump(),
        "competitor_names": result.task_plan.competitor_names,
        "decision_log": _stamp_decisions(result.decision_records, "task_plan"),
    }


_FALLBACK_BUCKET = "其他"


def _ensure_mapping_coverage(
    report_task: ReportTask, profiles: dict[str, dict],
) -> tuple[ReportTask, list[str]]:
    """Phase 2 fixup: dimension_canonical_map must cover every dim name in profiles.

    Missing dim names are auto-assigned to _FALLBACK_BUCKET; returns the updated
    report_task + the list of fallback dim names (for audit). Reporter treats
    _FALLBACK_BUCKET entries as supplementary info, excluded from the main ranking
    (see report_agent.md).
    """
    all_dim_names = {
        dim.get("name") for p in profiles.values()
        for dim in (p.get("dimensions") or [])
        if dim.get("name")
    }
    mapped = set(report_task.dimension_canonical_map.keys())
    missing = sorted(all_dim_names - mapped)
    if not missing:
        return report_task, []
    updated_map = {
        **report_task.dimension_canonical_map,
        **{name: _FALLBACK_BUCKET for name in missing},
    }
    return report_task.model_copy(update={"dimension_canonical_map": updated_map}), missing


def report_task_node(state: CCAState) -> dict:
    """Phase 3: build ReportTask (with analysis tasks) + decision records from
    profiles + review_state.

    Analyst has been folded into Reporter -- ReportTask carries both
    focus_dimensions/require_swot and sections/target_audience, which Reporter's
    ReAct loop uses to drive its internal analysis tools.

    After invoke, _ensure_mapping_coverage fixes up dimension_canonical_map,
    auto-assigning missing dim names to the fallback bucket.
    """
    profiles = state.get("profiles") or {}
    task_plan = state.get("task_plan") or {}
    result = cast(ReportTaskOutput, _invoke_pm(
        ReportTaskOutput, "阶段三 ReportTask",
        {
            "user_query": state["user_query"],
            "target_product": state["target_product"],
            "competitor_names": state.get("competitor_names", []),
            "profiles": profiles,
            "review_state": state.get("review_state", []),
            # tell the LLM about the buckets PM set in phase 2 so it reuses them in dimension_canonical_map
            "tentative_buckets": task_plan.get("tentative_buckets") or [],
        },
    ))
    coerced_task, fallback_dims = _ensure_mapping_coverage(result.report_task, profiles)
    updates: dict = {
        "report_task": coerced_task.model_dump(),
        "decision_log": _stamp_decisions(result.decision_records, "report_task"),
    }
    if fallback_dims:
        updates["audit_log"] = [{
            "agent": "pm", "event": "mapping_fallback_others",
            "fallback_dims": fallback_dims,
            "note": f"{len(fallback_dims)} 个 dim 未在 LLM mapping 中出现，自动归 '{_FALLBACK_BUCKET}'",
        }]
    emit_sse({"type": "progress", "pct": 72, "sec_left": 28})
    return updates


# ── Phase 2.5 human-in-the-loop gate (human_gate) ─────────────────────


def _human_review_enabled() -> bool:
    """Whether interactive human-in-the-loop is on (explicitly enabled by Streamlit/interactive runner).

    Off by default -- non-interactive paths (scripts/tests/cache-fill) must not pause,
    since interrupt() crashes without a checkpointer.
    """
    return os.getenv("CCA_HUMAN_REVIEW", "").lower() in ("1", "true", "on", "yes")


def _parse_feedback(raw: object) -> HumanReviewFeedback:
    """interrupt resume value -> HumanReviewFeedback. Tolerant: str is raw text, dict is
    validated, empty -> approved."""
    if not raw:
        return HumanReviewFeedback(approved=True)
    if isinstance(raw, str):
        return HumanReviewFeedback(raw_feedback=raw)
    if isinstance(raw, dict):
        return HumanReviewFeedback(**raw)
    return HumanReviewFeedback(approved=True)


def _profiles_digest(profiles: dict[str, dict]) -> list[dict]:
    """Frontend-facing summary table: one row per product with dimension names /
    review count / scraped platforms."""
    digest = []
    for name, profile in profiles.items():
        sentiment = profile.get("sentiment") or {}
        reviews = sentiment.get("representative_reviews") or []
        platforms = sorted({r.get("platform") for r in reviews if r.get("platform")})
        digest.append({
            "product_name": name,
            "dimensions": [d.get("name") for d in (profile.get("dimensions") or []) if d.get("name")],
            "review_count": len(reviews),
            "platforms": platforms,
            "has_pricing": bool(profile.get("pricing")),
        })
    return digest


def human_gate_node(state: CCAState) -> dict:
    """Human-in-the-loop gate before phase 2.5: collects the user's revision feedback
    on Collector/Insight output, once.

    Only pauses via interrupt() when CCA_HUMAN_REVIEW is on; non-interactive mode passes
    straight through. The human_review_done guard ensures a single pause -- the second
    arrival after a feedback-driven re-collect passes through directly. The guard must
    be checked before interrupt(), or the second arrival would trigger a brand-new pause.
    """
    if state.get("human_review_done"):
        return {}
    if not _human_review_enabled():
        return {"human_review_done": True}

    raw = interrupt({
        "kind": "human_review",
        "hint": "请对 Collector/Insight 的产出给出修订意见；留空或 approved=true 直接放行。",
        "profiles": _profiles_digest(state.get("profiles") or {}),
    })
    return {
        "human_review_done": True,
        "human_review_feedback": _parse_feedback(raw).model_dump(),
        "human_feedback_consumed": False,
    }


# ── Phase 2.5 Review ────────────────────────────────────────────────


def _check_data_completeness(
    profiles: dict[str, dict],
    task_plan: dict | None,
) -> dict[str, list[str]]:
    """Code-layer data-completeness precheck, producing pre_flags:
    {f"{agent}:{product}": ["data_missing: ...", ...]}.

    Only checks objective, naming-independent data quality: dimensions have facts /
    profile has sources / sentiment has enough reviews. Dimension alignment (bucket
    merging) is out of scope here -- that's Reporter's semantic dimension_canonical_map
    job and shouldn't block a re-collect via literal matching post-collection
    (see reroute / report_task).
    """
    flags: dict[str, list[str]] = {}
    if not task_plan:
        return flags

    for ct in task_plan.get("collect_tasks") or []:
        product = ct.get("product_name")
        if not product:
            continue
        unit_flags: list[str] = []
        profile = profiles.get(product) or {}
        dimensions = profile.get("dimensions") or []
        if not dimensions:
            unit_flags.append("data_missing: profile.dimensions 为空")
        else:
            for dim in dimensions:
                if not dim.get("facts"):
                    unit_flags.append(f"data_missing: dimension '{dim.get('name', '?')}' 无 fact")
        if not (profile.get("sources") or []):
            unit_flags.append("source_unreliable: profile.sources 为空")
        if unit_flags:
            flags[f"collector:{product}"] = unit_flags

    for it in task_plan.get("insight_tasks") or []:
        product = it.get("product_name")
        if not product:
            continue
        unit_flags = []
        profile = profiles.get(product) or {}
        sentiment = profile.get("sentiment")
        if not sentiment:
            unit_flags.append("data_missing: sentiment 字段为空")
        else:
            reviews = sentiment.get("representative_reviews") or []
            if len(reviews) < _SENTIMENT_MIN_REVIEWS:
                unit_flags.append(f"sentiment_too_few: {len(reviews)}/{_SENTIMENT_MIN_REVIEWS}")
        if unit_flags:
            flags[f"insight:{product}"] = unit_flags

    return flags


def _compute_retry_count(review_state: list[dict], agent: str, product: str) -> int:
    """Cumulative historical needs_retry / forced count for this (agent, product)."""
    return sum(
        1 for u in review_state
        if u.get("agent") == agent and u.get("product_name") == product
        and u.get("status") in ("needs_retry", "forced")
    )


def _enumerate_expected_units(task_plan: dict | None) -> list[tuple[str, str]]:
    """Enumerate every (agent, product_name) pair this round should produce, from task_plan."""
    if not task_plan:
        return []
    expected: list[tuple[str, str]] = []
    for ct in task_plan.get("collect_tasks") or []:
        if pn := ct.get("product_name"):
            expected.append(("collector", pn))
    for it in task_plan.get("insight_tasks") or []:
        if pn := it.get("product_name"):
            expected.append(("insight", pn))
    return expected


def _coerce_review_unit(
    unit: ReviewUnit,
    pre_flags: list[str],
    retry_count: int,
    reroute_count: int,
) -> ReviewUnit:
    """Plan-B hard constraints:
    1. all pre_flags get merged into qa_flags (the LLM can't drop any)
    2. non-empty pre_flags -> passed is disallowed
    3. retry_count is force-overwritten with the code-layer value
    4. reroute_count or unit retry_count at the limit -> needs_retry escalates to forced
    """
    merged_flags = list(unit.qa_flags)
    for pf in pre_flags:
        if pf not in merged_flags:
            merged_flags.append(pf)

    new_status = unit.status
    if pre_flags and new_status == "passed":
        new_status = "needs_retry"
    if new_status == "needs_retry" and (
        reroute_count >= _REROUTE_HARD_LIMIT or retry_count >= _PER_UNIT_RETRY_LIMIT
    ):
        new_status = "forced"

    return ReviewUnit(
        agent=unit.agent,
        product_name=unit.product_name,
        status=new_status,
        retry_count=retry_count,
        qa_flags=merged_flags,
        pm_note=unit.pm_note,
        reviewed_at=unit.reviewed_at or _now_iso(),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_retry_signal(unit: ReviewUnit) -> dict:
    """needs_retry ReviewUnit -> AgentSignal(data_gap) -> straight back to phase_2 (skips the reroute LLM).

    review's precheck always knows the root cause is phase_2, so reroute_phase is
    filled in directly and handle_signal skips the LLM diagnosis call.
    """
    return AgentSignal(
        from_agent=unit.agent,
        kind="data_gap",
        target="task_plan",
        payload=ChallengePayload(
            claim=f"{unit.agent}:{unit.product_name} 数据评审失败",
            evidence=unit.qa_flags or ["pre_check_failed"],
            suggested_fix="重新规划 task_plan 并 fanout 重采该产品",
        ),
        requires_debate=False,
        reroute_phase="phase_2",
        ts=_now_iso(),
    ).model_dump()


def review_node(state: CCAState) -> dict:
    """Phase 2.5: review Collector + Insight's concurrent output.

    Flow:
    1. code-layer _check_data_completeness -> pre_flags
    2. LLM ReviewOutput review (with pre_flags + retry_counts + profiles context)
    3. Plan-B post-check: non-empty pre_flags disallows passed; retry limit auto-escalates to forced
    4. needs_retry units -> AgentSignal(data_gap) -> next node (handle_signal) reroutes
    """
    profiles = state.get("profiles") or {}
    task_plan = state.get("task_plan")
    review_state = state.get("review_state") or []
    reroute_count = state.get("reroute_count") or 0

    pre_flags = _check_data_completeness(profiles, task_plan)
    expected = _enumerate_expected_units(task_plan)
    retry_counts = {
        f"{agent}:{product}": _compute_retry_count(review_state, agent, product)
        for agent, product in expected
    }

    # user's one-shot revision feedback: only counts this round if unconsumed; marked consumed=True after
    feedback_text = _human_feedback_text(state)
    use_feedback = bool(feedback_text) and not state.get("human_feedback_consumed")

    payload = {
        "expected_units": [f"{a}:{p}" for a, p in expected],
        "pre_flags": pre_flags,
        "retry_counts": retry_counts,
        "reroute_count": reroute_count,
        "reroute_hard_limit": _REROUTE_HARD_LIMIT,
        "per_unit_retry_limit": _PER_UNIT_RETRY_LIMIT,
        "profiles": profiles,
        "historical_review_state": review_state,
    }
    if use_feedback:
        payload["human_review_feedback"] = feedback_text
    # review has a full code-layer fallback (pre_flags alone can decide passed/needs_retry),
    # so the LLM isn't over-retried: a few attempts, then degrade to pure code-layer judgment
    # rather than let a flaky Doubao call take down the whole pipeline.
    try:
        result = cast(ReviewOutput, _invoke_pm(
            ReviewOutput, "阶段 2.5 Review", payload, max_attempts=_REVIEW_INVOKE_ATTEMPTS,
        ))
        llm_index = {(u.agent, u.product_name): u for u in result.review_units}
        decision_records = result.decision_records
        llm_degraded = False
    except RuntimeError as e:
        print(f"  [pm:review] LLM 评审失败，降级代码层判定：{e}", flush=True)
        llm_index = {}
        decision_records = [DecisionRecord(
            decision_type="other",
            chosen={"review_mode": "code_layer_fallback"},
            rationale="LLM 结构化评审连续失败，降级为代码层 pre_flags 判定；review 有完整兜底，不阻断流程。",
            inputs_used=["pre_flags"],
        )]
        llm_degraded = True

    # index LLM output by (agent, product) and coerce; missing expected units get a code-layer fallback ReviewUnit
    coerced: list[ReviewUnit] = []
    for agent, product in expected:
        key = f"{agent}:{product}"
        rc = retry_counts.get(key, 0)
        pre = pre_flags.get(key, [])
        if (agent, product) in llm_index:
            coerced.append(_coerce_review_unit(llm_index[(agent, product)], pre, rc, reroute_count))
        else:
            # LLM missed this unit -> code-layer fallback; status decided by the limit rules if pre_flags exist
            status = "passed" if not pre else (
                "forced" if rc >= _PER_UNIT_RETRY_LIMIT or reroute_count >= _REROUTE_HARD_LIMIT
                else "needs_retry"
            )
            coerced.append(ReviewUnit(
                agent=cast(Literal["collector", "insight"], agent),
                product_name=product,
                status=cast(Literal["passed", "needs_retry", "forced"], status),
                retry_count=rc,
                qa_flags=pre,
                pm_note="LLM 漏审，代码层兜底",
                reviewed_at=_now_iso(),
            ))

    signals = [_build_retry_signal(u) for u in coerced if u.status == "needs_retry"]

    updates: dict = {
        "review_state": [u.model_dump() for u in coerced],
        "agent_signals": signals,
        "decision_log": _stamp_decisions(decision_records, "review"),
        "audit_log": [{
            "agent": "pm", "event": "review_done",
            "passed": sum(1 for u in coerced if u.status == "passed"),
            "needs_retry": sum(1 for u in coerced if u.status == "needs_retry"),
            "forced": sum(1 for u in coerced if u.status == "forced"),
            "signals_raised": len(signals),
            "reroute_count": reroute_count,
            "llm_degraded": llm_degraded,
            "used_human_feedback": use_feedback,
        }],
    }
    # once feedback influences this round's judgment, mark it consumed: later rounds go
    # back to pure data review so the same feedback doesn't keep re-triggering retries
    if use_feedback:
        updates["human_feedback_consumed"] = True
    emit_sse({"type": "review_update", "units": [u.model_dump() for u in coerced]})
    emit_sse({"type": "progress", "pct": 68, "sec_left": 40})
    return updates


# ── Signal handling: debate (subjective) + reroute (factual) ─────────


def _read_defense(target: str, state: CCAState) -> DebatePosition:
    """Aggregate PM's defense position from same-phase decisions in decision_log, no LLM call."""
    log = state.get("decision_log") or []
    relevant = [d for d in log if d.get("phase") == target]
    if not relevant:
        return DebatePosition(
            agent_family=PM_FAMILY,
            claim=f"PM {target} 决策（decision_log 中无对应记录）",
            evidence=["state context"],
        )

    claims, evidence = [], []
    for d in relevant:
        dtype = d.get("decision_type", "other")
        claims.append(f"[{dtype}] {d.get('rationale', '')}")
        if chosen := d.get("chosen"):
            evidence.append(f"chosen[{dtype}]={chosen}")
        for alt in d.get("alternatives_considered") or []:
            if (opt := alt.get("option")) and (reason := alt.get("rejected_reason")):
                evidence.append(f"否决 {opt}：{reason}")
        for path in d.get("inputs_used") or []:
            if path:
                evidence.append(f"依据 {path}")

    return DebatePosition(
        agent_family=PM_FAMILY,
        claim=" | ".join(claims),
        evidence=evidence or ["决策上下文"],
    )


def _apply_debate_result(result: DebateResult) -> dict:
    """debate result -> state update: rejected clears the task; revision writes back; accepted just logs."""
    updates: dict = {
        "debate_results": [result.model_dump()],
        "audit_log": [{
            "agent": "pm", "event": "debate_applied",
            "target": result.target, "verdict": result.final_verdict,
        }],
    }
    task_field = _DEBATE_TARGET_TO_TASK_FIELD.get(result.target)

    if result.final_verdict == "rejected":
        if task_field:
            updates[task_field] = None
        return updates

    if result.revised_output and task_field:
        updates[task_field] = result.revised_output
        if result.target == "pm_taskplan":
            updates["competitor_names"] = result.revised_output.get("competitor_names", [])
    return updates


def _handle_debate_signal(signal: AgentSignal, state: CCAState) -> dict:
    """Subjective signal -> cross-family debate. Skipped in single-key mode (cross_family off),
    keeping the original output."""
    if not cross_family_enabled():
        return {"audit_log": [{
            "agent": "pm", "event": "cross_family_review_skipped",
            "target": signal.target, "reason": "single_key_mode",
        }]}
    challenge = DebatePosition(
        agent_family=CHALLENGER_FAMILY,
        claim=signal.payload.claim,
        evidence=signal.payload.evidence,
    )
    defense = _read_defense(signal.target, state)
    debate_target = cast(DebateTarget, _TARGET_TO_DEBATE.get(signal.target, "pm_taskplan"))
    target_content = state.get(signal.target) or {}
    result = run_debate(
        target=debate_target,
        target_content=target_content if isinstance(target_content, dict) else {},
        seed_positions={PM_FAMILY: defense, CHALLENGER_FAMILY: challenge},
    )
    return _apply_debate_result(result)


_REROUTE_CONTEXT_KEYS = (
    "exploration_result", "task_plan", "report_task", "review_state", "competitor_names",
)


def _build_reroute_context(state: CCAState) -> str:
    """Minimal state slice needed for reroute's root-cause analysis -- excludes big objects like profiles/logs."""
    slice_ = {k: state.get(k) for k in _REROUTE_CONTEXT_KEYS}
    return json.dumps(slice_, ensure_ascii=False, default=str)


def _handle_reroute_signal(signal: AgentSignal, state: CCAState) -> dict:
    """Factual signal -> phase rollback.

    If signal.reroute_phase is set (review's precheck data_gap) -> go straight back
    to that phase, skipping the LLM diagnosis; otherwise (e.g. Collector's
    request_product_replacement, ambiguous between phase_1/2) -> ask the reroute LLM.
    """
    if signal.reroute_phase:
        return apply_reroute_phase(signal.reroute_phase)
    return apply_reroute(reroute(signal, _build_reroute_context(state)))


def _phase_from_partial(partial: dict) -> str:
    """Infer reroute's target phase by working backward from which field got cleared."""
    if "exploration_result" in partial:
        return "phase_1"
    if "task_plan" in partial:
        return "phase_2"
    if "report_task" in partial:
        return "phase_3"
    return "phase_2"


def handle_signal_node(state: CCAState) -> dict:
    """Handle downstream AgentSignals.

    Dedup: signals already in state.consumed_signal_ids are skipped this round;
    newly-handled signal_ids are appended back.
    Order: reroute first (clears bad data) -> debate after (judges on clean state).
    """
    raw = state.get("agent_signals") or []
    if not raw:
        return {}

    consumed = set(state.get("consumed_signal_ids") or [])
    signals = [AgentSignal(**s) if isinstance(s, dict) else s for s in raw]
    pending = [s for s in signals if s.signal_id not in consumed]
    if not pending:
        return {}

    ordered = [s for s in pending if not s.requires_debate] + \
              [s for s in pending if s.requires_debate]

    debate_results, audit_log = [], []
    scalar_updates: dict = {}
    # reroute_count increments by at most 1 per handle_signal_node call (one loop = one
    # reroute cycle): stops a batch of 5 signals all triggering reroute at once from
    # jumping reroute_count straight to 5 and bypassing HARD_LIMIT=2.
    did_reroute = False
    new_reroute_count = (state.get("reroute_count") or 0) + 1
    for sig in ordered:
        if sig.requires_debate:
            partial = _handle_debate_signal(sig, state)
            for dr in partial.get("debate_results", []):
                emit_sse({
                    "type": "debate_result",
                    "target": dr.get("target"),
                    "final_verdict": dr.get("final_verdict"),
                    "judge_rationale": dr.get("judge_rationale"),
                })
        else:
            partial = _handle_reroute_signal(sig, state)
            if any(partial.get(k) is None and k in partial
                   for k in ("exploration_result", "task_plan", "report_task")):
                did_reroute = True
                emit_sse({
                    "type": "reroute",
                    "phase": sig.reroute_phase or _phase_from_partial(partial),
                    "count": new_reroute_count,
                    "reason": (sig.payload.claim if sig.payload else ""),
                })
        debate_results.extend(partial.pop("debate_results", []))
        audit_log.extend(partial.pop("audit_log", []))
        scalar_updates.update(partial)
    reroute_bumps = 1 if did_reroute else 0

    updates: dict = {
        **scalar_updates,
        "debate_results": debate_results,
        "audit_log": audit_log,
        "consumed_signal_ids": [s.signal_id for s in ordered],
    }
    if reroute_bumps:
        updates["reroute_count"] = (state.get("reroute_count") or 0) + reroute_bumps
    return updates
