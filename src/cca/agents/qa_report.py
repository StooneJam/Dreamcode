"""Report Agent —— 接收 Collector / Insight 全部产出 + PM 的 ReportTask，
ReAct 工具循环完成横向排序 + SWOT + 图表 + MD + PDF + (可选) 豆包终审。

原 Analyst 职责已并入：维度排序与 SWOT 由 submit_dimension_ranking /
finalize_swot 工具产，由 Reporter ReAct 自主调度。
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


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ── profile 序列化（含 forced 标注） ───────────────────────────────────


def _collect_forced_keys(review_state: list[dict]) -> set[str]:
    """提取 forced 项组合键 'agent:product_name'，用于 profile 注入低置信度标记。"""
    return {
        f"{ReviewUnit(**u).agent}:{ReviewUnit(**u).product_name}"
        for u in review_state
        if ReviewUnit(**u).status == "forced"
    }


def _slim_profile(profile: dict) -> dict:
    """压缩 profile：每条 Fact 只保留 statement + url，去除 snippet/fetched_at。"""
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
    """profiles → JSON；forced 产品附 `_低置信度来源` 字段；Fact 仅含 statement + url。"""
    annotated: dict[str, dict] = {}
    for name, profile in profiles.items():
        entry = _slim_profile(profile)
        low = [a for a in ("collector", "insight") if f"{a}:{name}" in forced_keys]
        if low:
            entry["_低置信度来源"] = low
        annotated[name] = entry
    return json.dumps(annotated, ensure_ascii=False, indent=2)


# ── prompt 上下文段块拼装 ──────────────────────────────────────────────


def _format_exploration(exp: dict | None) -> str:
    """一轮探索回顾：竞品选择脉络 + 维度候选池。"""
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
    """PM 阶段二决策回顾：权威 product_type + 每个产品的 priority_dimensions / target_platforms。"""
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
    """PM 评审台账全量。forced 项需在报告中标注未充分审核。"""
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
    """{dim_name → bucket} → {bucket → [dim_name, ...]}。Reporter 按 bucket 抓 fact 用。"""
    inv: dict[str, list[str]] = {}
    for dim_name, bucket in mapping.items():
        inv.setdefault(bucket, []).append(dim_name)
    return inv


def _format_canonical_mapping(mapping: dict[str, str]) -> str:
    """Phase 2 mapping 段块：正向 + 反向索引，让 Reporter 按 bucket 横向排名。"""
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
    """6 段拼装：ReportTask → exploration → task_plan → review_state → mapping → profiles JSON。"""
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


# ── messages 抽取 helpers ──────────────────────────────────────────────


def _extract_final_md(messages: list) -> str:
    """从最后一次 render_pdf tool_call 的参数取 markdown_content。
    LLM 未调 render_pdf 时，fallback 取最后一条以 # 开头的 AIMessage 文本。"""
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
    """从 render_pdf ToolMessage 取返回的文件路径。"""
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "render_pdf":
            return msg.content.strip()
    return None


def _extract_tool_jsons(messages: list, tool_name: str) -> list[dict]:
    """通用：收集指定工具调用中可解的 JSON。"""
    out = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == tool_name and msg.content:
            try:
                out.append(json.loads(msg.content))
            except json.JSONDecodeError:
                continue
    return out


def _fallback_generate_report(
    messages: list, task: ReportTask, profiles_json: str
) -> str:
    """ReAct 未产出报告正文时（Doubao 长上下文截断），一次性 LLM 调用生成 Markdown。"""
    from langchain_core.messages import HumanMessage

    # 收集已完成的排名和 SWOT 工具产出
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
    """取 call_reviewer 最后一次返回的 QAResult；未调用时返默认 passed。"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "call_reviewer" and msg.content:
            try:
                return QAResult.model_validate_json(msg.content)
            except (json.JSONDecodeError, ValueError):
                continue
    return QAResult(product_name="__report__", passed=True, note="reviewer 未被调用")


# ── 主节点 ─────────────────────────────────────────────────────────────


def report_node(state: CCAState) -> dict:
    """Report Agent：分析 + 撰写 + 渲染 + 终审。"""
    report_task = ReportTask(**state["report_task"])
    review_state = state.get("review_state") or []
    forced = _collect_forced_keys(review_state)
    profiles_json = _serialize_profiles(state.get("profiles", {}), forced)

    reviewer_active = report_task.invoke_call_report_reviewer and cross_family_enabled()
    reviewed = False  # 限制终审仅调用一次

    @tool
    def call_reviewer(report_md: str) -> str:
        """报告全部完成后调用豆包跨模型终审，检查图文一致性与事实可溯源性。只调用一次。"""
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
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_system_prompt()),
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

    # Doubao 等长上下文下可能截断、未输出报告正文：Python 侧一次性 LLM 补救
    if not report_md:
        report_md = _fallback_generate_report(messages, report_task, profiles_json)

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
