"""PM Agent —— 三阶段规划 + 信号分发，纯结构化 LLM 调用，无 ReAct 工具。

阶段节点：initial_brief / task_plan / report_task。下游信号统一进 handle_signal_node。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

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

# signal.target → debate target
_TARGET_TO_DEBATE = {
    "initial_brief": "pm_initial_brief",
    "task_plan": "pm_taskplan",
    "report_task": "report",
}
# debate target → 对应的 state 任务字段
_DEBATE_TARGET_TO_TASK_FIELD = {
    "pm_initial_brief": "initial_brief",
    "pm_taskplan": "task_plan",
    "report": "report_task",
}

# 单文档截断保护，防 prompt 爆
_MAX_FILE_CHARS = 50_000

PMPhase = Literal["initial_brief", "task_plan", "review", "report_task"]

# review_node 配置
_REROUTE_HARD_LIMIT = 2          # state.reroute_count 达此值后 needs_retry → forced
_PER_UNIT_RETRY_LIMIT = 2        # 单 (agent, product) 历史返工次数达此值后 needs_retry → forced
_SENTIMENT_MIN_REVIEWS = 1       # Insight sentiment 评论样本下限（1 条即可，不足时报告标注 forced）
_REVIEW_INVOKE_ATTEMPTS = 2      # review 有代码层兜底，LLM 不死磕：1 首次 + 1 retry，失败即降级


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _phase_prefix(phase: str) -> str:
    return f"## 当前阶段：{phase}\n\n"


def _stamp_decisions(records: list[DecisionRecord], phase: PMPhase) -> list[dict]:
    """落盘前强制覆盖 phase 字段，防 LLM 自报错值。"""
    out = []
    for r in records:
        d = r.model_dump()
        d["phase"] = phase
        out.append(d)
    return out


def _load_user_file(state: CCAState) -> tuple[str | None, str | None, list[dict]]:
    """读 state.user_files 第一个文件 → (path, text, audit)。多文件 / 失败仅记 audit，不抛。"""
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
    return path, text, audit


_PM_INVOKE_MAX_RETRIES = int(os.getenv("PM_INVOKE_MAX_RETRIES", "4"))


def _invoke_pm(output_type, phase_label: str, payload: dict, *, max_attempts: int | None = None):
    """PM 统一调用模板：with_structured_output + 失败自修。

    失败模式：
    1. ValidationError —— LLM 漏 required 字段：反馈错误详情让 LLM 修
    2. invoke 返 None —— LLM 用自由文本而非 function call 回答（Doubao 在复杂嵌套
       schema 上偶发）：显式强调必须用 function_call

    max_attempts 控制总尝试次数（含首次）。默认 _PM_INVOKE_MAX_RETRIES；有代码层兜底的
    节点（review）可传小值快速失败、不死磕。全部用尽仍失败 → raise，由调用方决定崩还是兜底。

    不接 cache —— 保留 LLM 在 schema 约束内的判断灵活度。
    """
    attempts = max_attempts or _PM_INVOKE_MAX_RETRIES
    llm = get_llm(PM_FAMILY).with_structured_output(output_type, method="function_calling")
    user = _phase_prefix(phase_label) + json.dumps(payload, ensure_ascii=False)
    messages = [SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]

    result = None
    last_error: str | None = None

    for attempt in range(attempts):
        try:
            current_messages = messages if attempt == 0 else messages + [HumanMessage(content=last_error)]
            result = llm.invoke(current_messages)
        except ValidationError as e:
            last_error = (
                f"上一次输出有 schema 错误，请严格按 {output_type.__name__} schema 重新输出。\n"
                f"错误详情：\n{e}\n\n"
                f"特别注意：DecisionRecord.rationale 是必填字符串，"
                f"每条 DecisionRecord 都必须有 rationale 字段。"
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

        return result

    raise RuntimeError(
        f"PM {phase_label} 节点在 {attempts} 次尝试后仍未获得结构化输出。"
        f"最后错误：{last_error}。"
        f"检查 model id 的 function_calling 支持，或 prompt 是否过长。"
    )


def initial_brief_node(state: CCAState) -> dict:
    """阶段一：消化 user_query + 可选文档，产 InitialBrief + 决策档案 + 可选 DomainSeed。"""
    file_path, file_text, file_audit = _load_user_file(state)
    payload: dict = {"user_query": state["user_query"]}
    if file_text is not None:
        payload["uploaded_file"] = {"path": file_path, "content": file_text}

    result = cast(InitialBriefOutput, _invoke_pm(
        InitialBriefOutput, "阶段一 InitialBrief", payload,
    ))

    updates: dict = {
        "initial_brief": result.initial_brief.model_dump(),
        # 回写精炼后的 target_product，作为 phase 1 之后的单一来源：下游（Collector 探索 /
        # 报告 / 前端摘要）统一读 state.target_product，避免「PM 精炼了 target 但报告读的还是
        # 入口原值」的分叉。原始用户输入仍保留在 state.user_query，不丢信息。
        "target_product": result.initial_brief.target_product,
        "decision_log": _stamp_decisions(result.decision_records, "initial_brief"),
    }
    if result.domain_seed is not None and file_path is not None:
        ds = result.domain_seed.model_dump()
        ds["source_files"] = [file_path]  # 代码端强制覆盖
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
    """state.human_review_feedback → 有实质修订时返原文，否则 None。"""
    raw = state.get("human_review_feedback")
    if not raw:
        return None
    fb = HumanReviewFeedback(**raw)
    return fb.raw_feedback if fb.has_revisions() else None


def task_plan_node(state: CCAState) -> dict:
    """阶段二：基于 exploration_result 产出 TaskPlan + 决策档案。

    若 state.human_review_feedback 含用户修订意见（feedback 驱动的 reroute 重排），
    把原文注入 payload，PM 据此解析分栏并调整 collect/insight 任务。
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
    """Phase 2 校正：dimension_canonical_map 必须覆盖 profiles 中所有 dim 名。

    缺漏的 dim 名自动归 _FALLBACK_BUCKET（"其他"），返新 report_task + fallback dim 名列表（供 audit）。
    Reporter 端遇到 _FALLBACK_BUCKET 时按"补充信息"形式处理，不进主排名（见 report_agent.md）。
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
    """阶段三：基于 profiles + review_state 产 ReportTask（含分析任务）+ 决策档案。

    Analyst 已并入 Reporter——ReportTask 同时携带 focus_dimensions / require_swot
    和 sections / target_audience，Reporter ReAct 据此调内部分析工具。

    Phase 2：invoke 后用 _ensure_mapping_coverage 校正 dimension_canonical_map，
    缺漏 dim 名自动归 "其他" 桶。
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
            # 让 LLM 知道 PM 阶段二定的 buckets，产 dimension_canonical_map 时优先沿用
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


# ── 阶段 2.5 人在环关卡（human_gate）─────────────────────────────────


def _human_review_enabled() -> bool:
    """是否启用交互式人在环（Streamlit/交互 runner 显式开启）。

    默认关闭——脚本/测试/cache-fill 等非交互路径不暂停，避免无 checkpointer 时 interrupt 崩。
    """
    return os.getenv("CCA_HUMAN_REVIEW", "").lower() in ("1", "true", "on", "yes")


def _parse_feedback(raw: object) -> HumanReviewFeedback:
    """interrupt resume 值 → HumanReviewFeedback。容错：str 当原文，dict 走校验，空 → approved。"""
    if not raw:
        return HumanReviewFeedback(approved=True)
    if isinstance(raw, str):
        return HumanReviewFeedback(raw_feedback=raw)
    if isinstance(raw, dict):
        return HumanReviewFeedback(**raw)
    return HumanReviewFeedback(approved=True)


def _profiles_digest(profiles: dict[str, dict]) -> list[dict]:
    """给前端展示用的摘要表：每个产品一行，列维度名 / 评论数 / 抓取平台。"""
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
    """阶段 2.5 前的人在环关卡：一次性收集用户对 Collector/Insight 产出的修订意见。

    仅 CCA_HUMAN_REVIEW 开启时 interrupt 暂停；非交互模式直接放行。
    human_review_done 守卫保证只暂停一次——feedback 驱动重采后第二次到达直接 pass-through。
    守卫必须在 interrupt() 之前判断，否则第二次到达会是全新 interrupt 再度暂停。
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


# ── 阶段 2.5 Review ─────────────────────────────────────────────────


def _check_data_completeness(
    profiles: dict[str, dict],
    task_plan: dict | None,
) -> dict[str, list[str]]:
    """代码层数据完整度预检，产 pre_flags：{f"{agent}:{product}": ["data_missing: ...", ...]}。

    只查客观、不依赖命名的数据质量：dimensions 有 fact / profile 有 sources / sentiment 有足够 reviews。
    维度对齐（bucket 归并）不在此 —— 那是 Reporter 的 dimension_canonical_map 语义任务，
    不该用字面匹配在采集后阻断重采（见 reroute / report_task）。
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
    """该 (agent, product) 历史 needs_retry / forced 累计次数。"""
    return sum(
        1 for u in review_state
        if u.get("agent") == agent and u.get("product_name") == product
        and u.get("status") in ("needs_retry", "forced")
    )


def _enumerate_expected_units(task_plan: dict | None) -> list[tuple[str, str]]:
    """从 task_plan 枚举本轮应产的全部 (agent, product_name) 对。"""
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
    """B 方案强约束：
    1. pre_flags 全量并入 qa_flags（不允许 LLM 遗漏）
    2. pre_flags 非空 → 禁止 passed
    3. retry_count 强制覆盖为代码层值
    4. reroute_count 或 unit retry_count 达上限 → needs_retry 升 forced
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
    """needs_retry ReviewUnit → AgentSignal(data_gap) → 直接回 phase_2 重排（跳过 reroute LLM）。

    review 预检已知根因恒为 phase_2，reroute_phase 直填，handle_signal 不再调 LLM 诊断。
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
    """阶段 2.5：评审 Collector + Insight 并发产出。

    流程：
    1. 代码层 _check_data_completeness → pre_flags
    2. LLM ReviewOutput 评审（含 pre_flags + retry_counts + profiles 上下文）
    3. B 方案 post-check：pre_flags 非空禁 passed；retry 上限自动升 forced
    4. needs_retry 单元 → AgentSignal(data_gap) → 下一节点 handle_signal 走 reroute
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

    # 用户一次性修订意见：仅在未消费时参与本轮判定，采纳后置 consumed=True 不再复用
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
    # review 有完整代码层兜底（pre_flags 足以独立判 passed/needs_retry），
    # 所以 LLM 不死磕：少量重试，连续失败即降级为纯代码层判定，绝不让 Doubao 抽风崩掉整条流程。
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

    # 索引 LLM 输出，按 (agent, product) 校正；缺失的 expected unit 用代码层兜底产 ReviewUnit
    coerced: list[ReviewUnit] = []
    for agent, product in expected:
        key = f"{agent}:{product}"
        rc = retry_counts.get(key, 0)
        pre = pre_flags.get(key, [])
        if (agent, product) in llm_index:
            coerced.append(_coerce_review_unit(llm_index[(agent, product)], pre, rc, reroute_count))
        else:
            # LLM 漏审 → 代码层兜底；存在 pre_flag 时按上限规则定 status
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
    # feedback 一旦参与本轮判定即标消费：后续轮次回归纯数据评审，避免同段意见反复触发返工
    if use_feedback:
        updates["human_feedback_consumed"] = True
    emit_sse({"type": "review_update", "units": [u.model_dump() for u in coerced]})
    emit_sse({"type": "progress", "pct": 68, "sec_left": 40})
    return updates


# ── 信号处理：debate（主观）+ reroute（事实性） ──────────────────────


def _read_defense(target: str, state: CCAState) -> DebatePosition:
    """从 decision_log 同 phase 决策聚合 PM 的辩护立场，零 LLM 调用。"""
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
    """debate 结果 → state 更新：rejected 清空 task；revision 写回；accepted 仅记账。"""
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
    """主观信号 → 跨家族 debate。单 key 模式（cross_family 关闭）跳过，保留原输出。"""
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
    """提供 reroute 根因分析所需的最小 state 切片——剔除 profiles / log 等大对象。"""
    slice_ = {k: state.get(k) for k in _REROUTE_CONTEXT_KEYS}
    return json.dumps(slice_, ensure_ascii=False, default=str)


def _handle_reroute_signal(signal: AgentSignal, state: CCAState) -> dict:
    """事实性信号 → 阶段回溯。

    signal.reroute_phase 非空（review 预检 data_gap）→ 直接回该阶段，跳过 LLM 诊断；
    否则（如 Collector request_product_replacement，phase_1/2 有歧义）→ reroute LLM 诊断。
    """
    if signal.reroute_phase:
        return apply_reroute_phase(signal.reroute_phase)
    return apply_reroute(reroute(signal, _build_reroute_context(state)))


def _phase_from_partial(partial: dict) -> str:
    """推断 reroute 回溯的目标阶段（从被清空的字段反推）。"""
    if "exploration_result" in partial:
        return "phase_1"
    if "task_plan" in partial:
        return "phase_2"
    if "report_task" in partial:
        return "phase_3"
    return "phase_2"


def handle_signal_node(state: CCAState) -> dict:
    """处理下游 AgentSignal。

    去重：state.consumed_signal_ids 中的信号本次跳过；新处理的 signal_id 累加回写。
    顺序：reroute 先（清脏数据）→ debate 后（基于干净状态裁决）。
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
    # reroute_count 每轮 handle_signal_node 最多 +1（一次循环 = 一次 reroute 周期）：
    # 防止一批 5 个 signal 同时触发 reroute 把 reroute_count 直接跳到 5 绕过 HARD_LIMIT=2。
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
