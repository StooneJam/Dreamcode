"""PM Agent —— 三阶段规划 + 信号分发，纯结构化 LLM 调用，无 ReAct 工具。

阶段节点：initial_brief / task_plan / report_task。下游信号统一进 handle_signal_node。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from cca.llm.factory import gpt
from cca.schema import (
    AgentFamily,
    AgentSignal,
    ChallengePayload,
    DebatePosition,
    DebateResult,
    DecisionRecord,
    InitialBriefOutput,
    ReportTask,
    ReportTaskOutput,
    ReviewOutput,
    ReviewUnit,
    TaskPlanOutput,
)
from cca.skills.debate import DebateTarget, run_debate
from cca.skills.reroute import apply_reroute, reroute
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
_SENTIMENT_MIN_REVIEWS = 3       # Insight sentiment 评论样本下限


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


def _invoke_pm(output_type, phase_label: str, payload: dict):
    """PM 统一调用模板：with_structured_output + 失败自修。

    失败模式：
    1. ValidationError —— LLM 漏 required 字段：反馈错误详情让 LLM 修
    2. invoke 返 None —— LLM 用自由文本而非 function call 回答（Doubao 在复杂嵌套
       schema 上偶发）：显式强调必须用 function_call，最多重试 PM_INVOKE_MAX_RETRIES 次

    不接 cache —— 保留 LLM 在 schema 约束内的判断灵活度。
    """
    llm = gpt.with_structured_output(output_type, method="function_calling")
    user = _phase_prefix(phase_label) + json.dumps(payload, ensure_ascii=False)
    messages = [SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]

    result = None
    last_error: str | None = None

    for attempt in range(_PM_INVOKE_MAX_RETRIES):
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
            print(f"  [pm:{phase_label}] WARN: LLM 返 None（attempt {attempt + 1}/{_PM_INVOKE_MAX_RETRIES}），retry", flush=True)
            continue

        return result

    raise RuntimeError(
        f"PM {phase_label} 节点在 {_PM_INVOKE_MAX_RETRIES} 次重试后仍未获得结构化输出。"
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
        "decision_log": _stamp_decisions(result.decision_records, "initial_brief"),
    }
    if result.domain_seed is not None and file_path is not None:
        ds = result.domain_seed.model_dump()
        ds["source_files"] = [file_path]  # 代码端强制覆盖
        updates["domain_seed"] = ds
    if file_audit:
        updates["audit_log"] = file_audit
    return updates


def task_plan_node(state: CCAState) -> dict:
    """阶段二：基于 exploration_result 产出 TaskPlan + 决策档案。"""
    result = cast(TaskPlanOutput, _invoke_pm(
        TaskPlanOutput, "阶段二 TaskPlan",
        {
            "user_query": state["user_query"],
            "exploration_result": state.get("exploration_result", {}),
            "competitor_names": state.get("competitor_names", []),
        },
    ))
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
            # Phase 2: 让 LLM 知道 PM 阶段二定的 buckets，产 mapping 时优先沿用
            "tentative_buckets": task_plan.get("tentative_buckets") or [],
            "bucket_keywords": task_plan.get("bucket_keywords") or [],
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
    return updates


# ── 阶段 2.5 Review ─────────────────────────────────────────────────


def _bucket_keywords_to_dict(raw: list[dict] | dict | None) -> dict[str, list[str]]:
    """task_plan["bucket_keywords"] 归一为 dict[str, list[str]]。

    兼容两种存储形态：
    - list[BucketKeywords.model_dump()] = list[{bucket, keywords}]（schema 现态）
    - dict[str, list[str]]（旧形态或测试直接构造）
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return {item["bucket"]: item["keywords"] for item in raw if "bucket" in item}


def _bucket_coverage_flags(
    dim_names: list[str],
    tentative_buckets: list[str],
    bucket_keywords: dict[str, list[str]],
) -> list[str]:
    """单产品 → bucket_uncovered flag list。纯函数，无 task_plan 上下文。

    判定：bucket 的 keywords 中任一 substring 命中任一 dim_name → 视为覆盖。
    keywords 缺失（如 bucket_keywords 没该 bucket 条目）→ 跳过该 bucket（不报 flag，PM TaskPlan validator 已强校验同步性，理论不应到这）。
    tentative_buckets 为空 → 返空列表（Phase 2 机制关闭场景）。
    """
    if not tentative_buckets:
        return []
    return [
        f"bucket_uncovered: {bucket}"
        for bucket in tentative_buckets
        if bucket_keywords.get(bucket)
        and not any(kw in name for name in dim_names for kw in bucket_keywords[bucket])
    ]


def _check_data_completeness(
    profiles: dict[str, dict],
    task_plan: dict | None,
) -> dict[str, list[str]]:
    """代码层数据完整度预检，产 pre_flags：{f"{agent}:{product}": ["data_missing: ...", ...]}。

    Phase 1：dimensions 有 fact / profile 有 sources / sentiment 有足够 reviews。
    Phase 2：collector 循环内追加 bucket_uncovered 检查（通过 _bucket_coverage_flags）。
    """
    flags: dict[str, list[str]] = {}
    if not task_plan:
        return flags

    tentative_buckets = task_plan.get("tentative_buckets") or []
    bucket_keywords = _bucket_keywords_to_dict(task_plan.get("bucket_keywords"))

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
        # Phase 2: bucket 覆盖检查（dim 名 substring 比对 bucket_keywords）
        unit_flags.extend(_bucket_coverage_flags(
            [dim.get("name", "") for dim in dimensions],
            tentative_buckets, bucket_keywords,
        ))
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
    """needs_retry ReviewUnit → AgentSignal(data_gap, requires_debate=False) → reroute → phase_2。"""
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

    payload = {
        "expected_units": [f"{a}:{p}" for a, p in expected],
        "pre_flags": pre_flags,
        "retry_counts": retry_counts,
        "reroute_count": reroute_count,
        "reroute_hard_limit": _REROUTE_HARD_LIMIT,
        "per_unit_retry_limit": _PER_UNIT_RETRY_LIMIT,
        "profiles": profiles,
        "historical_review_state": review_state,
        # Phase 2: LLM 须知本轮 bucket 设定，便于判断 pre_flags 中 bucket_uncovered 的根因
        "tentative_buckets": (task_plan or {}).get("tentative_buckets") or [],
        "bucket_keywords": (task_plan or {}).get("bucket_keywords") or [],
    }
    result = cast(ReviewOutput, _invoke_pm(ReviewOutput, "阶段 2.5 Review", payload))

    # 索引 LLM 输出，按 (agent, product) 校正；缺失的 expected unit 用代码层兜底产 ReviewUnit
    llm_index = {(u.agent, u.product_name): u for u in result.review_units}
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

    return {
        "review_state": [u.model_dump() for u in coerced],
        "agent_signals": signals,
        "decision_log": _stamp_decisions(result.decision_records, "review"),
        "audit_log": [{
            "agent": "pm", "event": "review_done",
            "passed": sum(1 for u in coerced if u.status == "passed"),
            "needs_retry": sum(1 for u in coerced if u.status == "needs_retry"),
            "forced": sum(1 for u in coerced if u.status == "forced"),
            "signals_raised": len(signals),
            "reroute_count": reroute_count,
        }],
    }


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
    """主观信号 → 跨家族 debate。"""
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
    """事实性信号 → reroute skill 根因分析 + 阶段回溯。"""
    return apply_reroute(reroute(signal, _build_reroute_context(state)))


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
    # reroute_bumps 最多 +1 per handle_signal_node 调用（一次循环 = 一次 reroute 周期）
    # 防止一批 5 个 signal 同时触发 reroute，让 reroute_count 直接跳到 5 绕过 HARD_LIMIT=2
    did_reroute = False
    for sig in ordered:
        if sig.requires_debate:
            partial = _handle_debate_signal(sig, state)
        else:
            partial = _handle_reroute_signal(sig, state)
            if any(partial.get(k) is None and k in partial
                   for k in ("exploration_result", "task_plan", "report_task")):
                did_reroute = True
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
