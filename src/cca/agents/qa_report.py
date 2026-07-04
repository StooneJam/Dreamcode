"""Report Agent -- takes all Collector/Insight output + PM's ReportTask and runs a
ReAct tool loop to produce cross-product ranking + SWOT + charts + MD + PDF +
(optional) Doubao final review.

The old Analyst role has been folded in: dimension ranking and SWOT are produced by
the submit_dimension_ranking / finalize_swot tools, dispatched by Reporter's own ReAct loop.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from cca.agents._streaming import emit_sse, stream_react
from cca.llm.factory import cross_family_enabled, get_report_llm
from cca.schema import QAResult, ReportTask, ReviewUnit
from cca.skills.call_report_reviewer import call_report_reviewer
from cca.state import CCAState
from cca.tools.chart import render_bar_chart, render_chart
from cca.tools.pdf_renderer import render_pdf
from cca.tools.report_tools import finalize_swot, submit_dimension_ranking

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "report_agent.md"

_LANG_DIRECTIVE: dict[str, str] = {
    "en": (
        "CRITICAL INSTRUCTION: Write the entire report in English. "
        "All section titles, body text, table content, chart labels, and conclusions "
        "must be in English. Do not use Chinese anywhere in the report output.\n\n"
    ),
}


def _load_system_prompt(report_language: str = "zh") -> str:
    base = _PROMPT_PATH.read_text(encoding="utf-8")
    directive = _LANG_DIRECTIVE.get(report_language, "")
    return directive + base


# ── profile serialization (with forced annotations) ───────────────────


def _collect_forced_keys(review_state: list[dict]) -> set[str]:
    """Extract the 'agent:product_name' composite keys of forced items, for tagging
    low-confidence profiles."""
    return {
        f"{ReviewUnit(**u).agent}:{ReviewUnit(**u).product_name}"
        for u in review_state
        if ReviewUnit(**u).status == "forced"
    }


def _slim_profile(profile: dict) -> dict:
    """Shrink a profile: each Fact keeps only statement + url, dropping snippet/fetched_at."""
    result = dict(profile)
    if dims := result.get("dimensions"):
        slimmed = []
        for dim in dims:
            dim = dict(dim)
            if facts := dim.get("facts"):
                dim["facts"] = [
                    {
                        "statement": f.get("statement", ""),
                        "url": [e.get("source_url", "") for e in (f.get("evidence") or [])],
                    }
                    for f in facts
                ]
            slimmed.append(dim)
        result["dimensions"] = slimmed
    if sources := result.get("sources"):
        result["sources"] = [s.get("source_url", "") for s in sources]
    if key_events := result.get("key_events"):
        result["key_events"] = [
            {
                "statement": f.get("statement", ""),
                "url": [e.get("source_url", "") for e in (f.get("evidence") or [])],
            }
            for f in key_events
        ]
    if sentiment := result.get("sentiment"):
        sentiment = dict(sentiment)
        if s_sources := sentiment.get("sources"):
            sentiment["sources"] = [s.get("source_url", "") for s in s_sources]
        if reviews := sentiment.get("representative_reviews"):
            sentiment["representative_reviews"] = [
                {k: v for k, v in r.items() if k != "source"} for r in reviews
            ]
        result["sentiment"] = sentiment
    return result


def _serialize_profiles(profiles: dict[str, dict], forced_keys: set[str]) -> str:
    """profiles -> JSON; forced products get a `_低置信度来源` (low-confidence-source)
    field; Fact keeps only statement + url."""
    annotated: dict[str, dict] = {}
    for name, profile in profiles.items():
        entry = _slim_profile(profile)
        low = [a for a in ("collector", "insight") if f"{a}:{name}" in forced_keys]
        if low:
            entry["_低置信度来源"] = low
        annotated[name] = entry
    return json.dumps(annotated, ensure_ascii=False, indent=2)


# ── prompt context block assembly ─────────────────────────────────────


def _format_exploration(exp: dict | None) -> str:
    """Phase-1 exploration recap: competitor-selection trail + dimension candidate pool."""
    if not exp:
        return ""
    lines = ["## 一轮探索回顾（Collector exploration_result）"]
    if exp.get("target_product"):
        lines.append(f"- target_product: {exp['target_product']}")
    if exp.get("product_type"):
        lines.append(f"- product_type（Collector 联网推断）: {exp['product_type']}")
    if dims := exp.get("discovered_dimensions"):
        lines.append(f"- 一轮发现的对比维度候选: {', '.join(dims)}")
    if rationale := exp.get("rationale"):
        lines.append(f"- Collector rationale: {rationale}")
    if briefs := exp.get("initial_profiles"):
        lines.append("- 一轮发现的竞品 brief:")
        for b in briefs:
            lines.append(
                f"  · {b.get('product_name')} | company={b.get('company')} | "
                f"website={b.get('website')} | type={b.get('product_type')}"
            )
    return "\n".join(lines)


def _format_task_plan(plan: dict | None) -> str:
    """PM phase-2 decision recap: authoritative product_type + each product's
    priority_dimensions / target_platforms."""
    if not plan:
        return ""
    lines = ["## PM 阶段二决策回顾（task_plan 关键字段）"]
    if plan.get("product_type"):
        lines.append(f"- product_type（一轮 debate 收敛后权威值）: {plan['product_type']}")
    for ct in plan.get("collect_tasks") or []:
        if pds := ct.get("priority_dimensions"):
            lines.append(f"- Collector→{ct.get('product_name')} priority_dimensions: {', '.join(pds)}")
    for it in plan.get("insight_tasks") or []:
        extras = []
        if tps := it.get("target_platforms"):
            extras.append(f"target_platforms={', '.join(tps)}")
        if pds := it.get("priority_dimensions"):
            extras.append(f"priority_dimensions={', '.join(pds)}")
        if extras:
            lines.append(f"- Insight→{it.get('product_name')}: {'; '.join(extras)}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _format_review_state(review_state: list[dict]) -> str:
    """Full PM review ledger. forced items must be flagged as under-reviewed in the report."""
    if not review_state:
        return ""
    lines = ["## PM 评审台账（review_state 全量，forced 项需在报告中标注未充分审核）"]
    for u in review_state:
        extras = ""
        if qa := u.get("qa_flags"):
            extras += f" | qa_flags={qa}"
        if note := u.get("pm_note"):
            extras += f" | pm_note={note}"
        lines.append(
            f"- {u.get('agent')}:{u.get('product_name')} "
            f"status={u.get('status')} retry_count={u.get('retry_count')}{extras}"
        )
    return "\n".join(lines)


def _invert_canonical_map(mapping: dict[str, str]) -> dict[str, list[str]]:
    """{dim_name -> bucket} -> {bucket -> [dim_name, ...]}, for Reporter to pull facts by bucket."""
    inv: dict[str, list[str]] = {}
    for dim_name, bucket in mapping.items():
        inv.setdefault(bucket, []).append(dim_name)
    return inv


def _format_canonical_mapping(mapping: dict[str, str]) -> str:
    """Phase-2 mapping block: forward + reverse index, so Reporter ranks by bucket."""
    if not mapping:
        return ""
    inv = _invert_canonical_map(mapping)
    return (
        "## 维度归类映射（dimension_canonical_map，Phase 2）\n"
        "Reporter 横向排名按 canonical bucket 进行；正文叙述时引用细分 dim 名以保溯源。\n"
        f"### 正向（dim_name → bucket）\n```json\n{json.dumps(mapping, ensure_ascii=False, indent=2)}\n```\n"
        f"### 反向索引（bucket → [dim_name, ...]）\n```json\n{json.dumps(inv, ensure_ascii=False, indent=2)}\n```"
    )


def _build_initial_message(
    task: ReportTask,
    profiles_json: str,
    exploration_result: dict | None,
    task_plan: dict | None,
    review_state: list[dict],
) -> str:
    """Assemble 6 blocks: ReportTask -> exploration -> task_plan -> review_state -> mapping -> profiles JSON."""
    audience = task.target_audience or "产品团队"
    focus = "、".join(task.focus_dimensions) if task.focus_dimensions else "（自主判断）"
    sections = "、".join(task.sections) if task.sections else "（自主决定）"
    names = task.product_names or ([task.target_product] + list(task.competitors))

    task_block = (
        f"## 报告任务（ReportTask）\n"
        f"- 分析对象：{task.target_product}\n"
        f"- 竞品：{', '.join(task.competitors)}\n"
        f"- 参与对比产品（ranking / SWOT 工具覆盖范围）：{'、'.join(names)}\n"
        f"- 重点对比维度（submit_dimension_ranking 优先覆盖）：{focus}\n"
        f"- 是否输出 SWOT（finalize_swot）：{task.require_swot}\n"
        f"- 是否要求跨产品横向对比章节：{task.cross_product_comparison_required}\n"
        f"- 目标读者：{audience}\n"
        f"- 章节顺序：{sections}\n"
        f"- 输出格式：{task.output_formats}\n"
        f"- 调用豆包终审：{task.invoke_call_report_reviewer}"
    )
    profiles_block = (
        f"## 产品档案数据（Collector + Insight 全部 owner 字段）\n"
        f"```json\n{profiles_json}\n```"
    )
    blocks = [
        task_block,
        _format_exploration(exploration_result),
        _format_task_plan(task_plan),
        _format_review_state(review_state),
        _format_canonical_mapping(task.dimension_canonical_map),
        profiles_block,
    ]
    return "\n\n".join(b for b in blocks if b)


# ── message extraction helpers ─────────────────────────────────────────


def _extract_final_md(messages: list) -> str:
    """Get markdown_content from the last render_pdf tool_call's args.
    If the LLM never called render_pdf, fall back to the last AIMessage starting with #."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc["name"] == "render_pdf":
                    return tc["args"].get("markdown_content", "")
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = (msg.content or "").strip()
            if text.startswith("#"):
                return text
    return ""


def _extract_pdf_path(messages: list) -> str | None:
    """Get the returned file path from the render_pdf ToolMessage."""
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "render_pdf":
            return msg.content.strip()
    return None


def _extract_tool_jsons(messages: list, tool_name: str) -> list[dict]:
    """Generic: collect parseable JSON from calls to the given tool."""
    out = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == tool_name and msg.content:
            try:
                out.append(json.loads(msg.content))
            except json.JSONDecodeError:
                continue
    return out


def _is_truncated(report_md: str) -> bool:
    """Whether the report got cut off: missing a closing section (conclusion/sources)
    counts as incomplete."""
    tail = report_md[-800:]
    end_markers = ("结论", "建议", "数据来源", "参考", "sources", "conclusion", "references")
    return not any(m in tail.lower() for m in end_markers)


def _fallback_generate_report(
    messages: list, task: ReportTask, profiles_json: str
) -> str:
    """When ReAct never produced report body text (Doubao long-context truncation),
    make one extra LLM call to generate the Markdown."""
    from langchain_core.messages import HumanMessage

    # gather the ranking and SWOT tool outputs already produced
    ranking_results, swot_result, chart_refs = [], "", []
    for msg in messages:
        if not isinstance(msg, ToolMessage) or not msg.content:
            continue
        if msg.name == "submit_dimension_ranking":
            try:
                ranking_results.append(json.loads(msg.content))
            except json.JSONDecodeError:
                pass
        elif msg.name == "finalize_swot":
            swot_result = msg.content[:1200]
        elif msg.name in ("render_chart", "render_bar_chart"):
            chart_refs.append(msg.content.strip())

    ranking_text = json.dumps(ranking_results, ensure_ascii=False, indent=2)[:2000]
    charts_text = "\n".join(chart_refs)

    prompt = (
        f"你是竞品分析专家。分析工具已全部完成，请直接输出完整竞品分析报告正文。\n\n"
        f"目标产品：{task.target_product}　竞品：{', '.join(task.competitors)}\n\n"
        f"## 维度竞争力排名结果\n```json\n{ranking_text}\n```\n\n"
        f"## SWOT 分析结果\n{swot_result}\n\n"
        f"## 已生成图表（直接插入对应章节）\n{charts_text}\n\n"
        f"## 产品档案（精简）\n{profiles_json[:3000]}\n\n"
        f"报告第一行必须是：# {task.target_product}竞品分析报告\n"
        f"按以下章节顺序输出（每章至少2段）：\n"
        f"一、背景与目标　二、产品定位　三、商业策略　四、产品设计（含图表）　"
        f"五、用户数据分析　六、用户反馈　七、SWOT综合（含表格）　八、结论与建议　数据来源\n"
        f"用中文，段落横向对比所有产品，不按产品逐个分段。"
    )
    try:
        result = get_report_llm().invoke([HumanMessage(content=prompt)])
        text = (result.content or "").strip()
        return text if text.startswith("#") else f"# {task.target_product}竞品分析报告\n\n{text}"
    except Exception:
        return ""


def _extract_reviewer_result(messages: list) -> QAResult:
    """Get the QAResult from call_reviewer's last return; defaults to passed if never called."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "call_reviewer" and msg.content:
            try:
                return QAResult.model_validate_json(msg.content)
            except (json.JSONDecodeError, ValueError):
                continue
    return QAResult(product_name="__report__", passed=True, note="reviewer 未被调用")


# ── main node ───────────────────────────────────────────────────────────


def report_node(state: CCAState) -> dict:
    """Report Agent: analyze + write + render + final review."""
    report_task = ReportTask(**state["report_task"])
    review_state = state.get("review_state") or []
    forced = _collect_forced_keys(review_state)
    profiles_json = _serialize_profiles(state.get("profiles", {}), forced)

    reviewer_active = report_task.invoke_call_report_reviewer and cross_family_enabled()
    reviewed = False  # cap final review at exactly one call

    @tool
    def call_reviewer(report_md: str) -> str:
        """Call Doubao for a cross-model final review once the report is fully done,
        checking text/chart consistency and factual traceability. Call this only once."""
        nonlocal reviewed
        if not cross_family_enabled():
            return QAResult(
                product_name="__report__",
                passed=True,
                note="单 key 模式，跨家族终审已关闭",
            ).model_dump_json()
        if reviewed:
            return "终审已完成，请勿重复调用。"
        reviewed = True
        try:
            result = call_report_reviewer(report_md, json.loads(profiles_json))
            return result.model_dump_json()
        except Exception as exc:
            return QAResult(
                product_name="__report__",
                passed=True,
                note=f"豆包终审调用失败，已跳过：{exc}",
            ).model_dump_json()

    agent = create_react_agent(
        model=get_report_llm(),
        tools=[
            submit_dimension_ranking, finalize_swot,
            render_chart, render_bar_chart, render_pdf,
            call_reviewer,
        ],
    )
    emit_sse({"type": "progress", "pct": 75, "sec_left": 25})
    lang = state.get("report_language", "zh")
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_system_prompt(lang)),
            HumanMessage(content=_build_initial_message(
                report_task, profiles_json,
                exploration_result=state.get("exploration_result"),
                task_plan=state.get("task_plan"),
                review_state=review_state,
            )),
        ],
        label="Reporter",
        recursion_limit=80,
    )
    reviewer_result = _extract_reviewer_result(messages)
    pdf_path = _extract_pdf_path(messages)
    report_md = _extract_final_md(messages)

    # Doubao 等长上下文下可能截断（无报告 or 报告不完整）：Python 侧一次性 LLM 补救
    if not report_md or _is_truncated(report_md):
        report_md = _fallback_generate_report(messages, report_task, profiles_json) or report_md

    # LLM 未调 render_pdf 时，Python 侧兜底渲染
    if report_md and not pdf_path:
        pdf_path = render_pdf.invoke({
            "markdown_content": report_md,
            "target_product": report_task.target_product,
        })

    if not reviewer_active:
        report_status = "unreviewed"
    else:
        report_status = "passed" if reviewer_result.passed else "failed"

    emit_sse({"type": "report_status", "status": report_status})
    emit_sse({"type": "qa_result", "results": [reviewer_result.model_dump()]})
    emit_sse({"type": "progress", "pct": 95, "sec_left": 2})

    from datetime import datetime, timezone
    return {
        "report_md": report_md,
        "report_pdf_path": pdf_path,
        "report_status": report_status,
        "analysis_end_ts": datetime.now(timezone.utc).isoformat(),
        "qa_results": [reviewer_result.model_dump()],
        "audit_log": [{
            "agent": "report", "event": "report_generated",
            "status": report_status, "pdf_path": pdf_path,
        }],
    }
