"""PM Agent —— 三阶段规划 + 信号分发，纯结构化 LLM 调用，无 ReAct 工具。

阶段节点：initial_brief / task_plan / report_task。下游信号统一进 handle_signal_node。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from cca.llm.factory import gpt
from cca.memory import react_cache
from cca.schema import (
    AgentFamily,
    AgentSignal,
    DebatePosition,
    DebateResult,
    DecisionRecord,
    InitialBriefOutput,
    ReportTaskOutput,
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
_TARGET_TO_DEBATE = {"task_plan": "pm_taskplan", "report_task": "report"}
# debate target → 对应的 state 任务字段
_DEBATE_TARGET_TO_TASK_FIELD = {"pm_taskplan": "task_plan", "report": "report_task"}

# 单文档截断保护，防 prompt 爆
_MAX_FILE_CHARS = 50_000

PMPhase = Literal["initial_brief", "task_plan", "report_task"]


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


def _invoke_pm(output_type, phase_label: str, payload: dict, cache_node: str | None = None):
    """PM 统一调用模板：cache hook + with_structured_output + 一次 schema 自修重试。

    function_calling 不保证 100% schema 合规（GPT-5 偶尔漏 required 字段），
    捕到 ValidationError 把错误反馈给 LLM 再调一次。

    cache_node 非 None 且 CCA_CACHE_MODE 允许时：replay 直接反序列化 cached JSON；
    write/auto 真跑后落 SQLite。详见 D-036 / DP-006。
    """
    mode = react_cache.get_mode()
    use_cache = cache_node is not None
    cache_key = {"phase": phase_label, "payload": payload} if use_cache else None

    if use_cache and mode in ("replay", "auto"):
        cached = react_cache.get(cache_node, cache_key)
        if cached is not None:
            print(f"  [pm:{cache_node}] (cache replay)", flush=True)
            return output_type.model_validate_json(cached["json"])
        if mode == "replay":
            raise RuntimeError(
                f"[react_cache] mode=replay 但 PM 缓存未命中：node={cache_node}。请先 mode=write 跑一次。"
            )

    llm = gpt.with_structured_output(output_type, method="function_calling")
    user = _phase_prefix(phase_label) + json.dumps(payload, ensure_ascii=False)
    messages = [SystemMessage(content=_load_system_prompt()), HumanMessage(content=user)]
    try:
        result = llm.invoke(messages)
    except ValidationError as e:
        repair = HumanMessage(content=(
            f"上一次输出有 schema 错误，请严格按 {output_type.__name__} schema 重新输出。\n"
            f"错误详情：\n{e}\n\n"
            f"特别注意：DecisionRecord.rationale 是必填字符串，"
            f"每条 DecisionRecord 都必须有 rationale 字段。"
        ))
        result = llm.invoke(messages + [repair])

    if use_cache and mode in ("write", "auto"):
        react_cache.put(cache_node, cache_key, {"json": result.model_dump_json()})
        print(f"  [pm:{cache_node}] (cache write)", flush=True)
    return result


def initial_brief_node(state: CCAState) -> dict:
    """阶段一：消化 user_query + 可选文档，产 InitialBrief + 决策档案 + 可选 DomainSeed。"""
    file_path, file_text, file_audit = _load_user_file(state)
    payload: dict = {"user_query": state["user_query"]}
    if file_text is not None:
        payload["uploaded_file"] = {"path": file_path, "content": file_text}

    result = cast(InitialBriefOutput, _invoke_pm(
        InitialBriefOutput, "阶段一 InitialBrief", payload,
        cache_node="pm.initial_brief",
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
        cache_node="pm.task_plan",
    ))
    return {
        "task_plan": result.task_plan.model_dump(),
        "competitor_names": result.task_plan.competitor_names,
        "decision_log": _stamp_decisions(result.decision_records, "task_plan"),
    }


def report_task_node(state: CCAState) -> dict:
    """阶段三：基于 profiles + review_state 产 ReportTask（含分析任务）+ 决策档案。

    Analyst 已并入 Reporter——ReportTask 同时携带 focus_dimensions / require_swot
    和 sections / target_audience，Reporter ReAct 据此调内部分析工具。
    """
    result = cast(ReportTaskOutput, _invoke_pm(
        ReportTaskOutput, "阶段三 ReportTask",
        {
            "user_query": state["user_query"],
            "target_product": state["target_product"],
            "competitor_names": state.get("competitor_names", []),
            "profiles": state.get("profiles", {}),
            "review_state": state.get("review_state", []),
        },
        cache_node="pm.report_task",
    ))
    return {
        "report_task": result.report_task.model_dump(),
        "decision_log": _stamp_decisions(result.decision_records, "report_task"),
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
    for sig in ordered:
        partial = _handle_debate_signal(sig, state) if sig.requires_debate \
                  else _handle_reroute_signal(sig, state)
        debate_results.extend(partial.pop("debate_results", []))
        audit_log.extend(partial.pop("audit_log", []))
        scalar_updates.update(partial)

    return {
        **scalar_updates,
        "debate_results": debate_results,
        "audit_log": audit_log,
        "consumed_signal_ids": [s.signal_id for s in ordered],
    }
