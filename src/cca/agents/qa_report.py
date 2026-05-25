"""Report Agent —— 整合上游产出，生成 MD + PDF 竞品分析报告。

架构位置：Phase 3，接收 Collector / Insight / Analyst 全部产出 + PM 下发的 ReportTask。
使用 create_react_agent 实现真正的工具调用循环，Agent 自主决定生成哪些图表、如何组织章节。
豆包终审通过 call_report_reviewer skill 调用（D-017）。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from cca.llm.factory import gpt
from cca.schema import AgentSignal, ChallengePayload, QAResult, ReportTask, ReviewUnit
from cca.skills.call_report_reviewer import call_report_reviewer
from cca.state import CCAState
from cca.tools.chart import render_bar_chart, render_chart
from cca.tools.pdf_renderer import render_pdf

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "report_agent.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _collect_forced_keys(review_state: list[dict]) -> set[str]:
    """提取所有 forced 放行的 (agent, product) 组合键，格式为 'agent:product_name'。"""
    return {
        f"{ReviewUnit(**u).agent}:{ReviewUnit(**u).product_name}"
        for u in review_state
        if ReviewUnit(**u).status == "forced"
    }


def _serialize_profiles(profiles: dict[str, dict], forced_keys: set[str]) -> str:
    """序列化产品档案为 JSON，并为置信度低的数据注入标注字段。"""
    annotated: dict[str, dict] = {}
    for name, profile in profiles.items():
        entry = dict(profile)
        low_confidence = [
            agent for agent in ("collector", "insight", "analyst")
            if f"{agent}:{name}" in forced_keys
        ]
        if low_confidence:
            entry["_低置信度来源"] = low_confidence
        annotated[name] = entry
    return json.dumps(annotated, ensure_ascii=False, indent=2)


def _build_initial_message(task: ReportTask, profiles_json: str) -> str:
    """构造发给 Agent 的初始任务消息，包含 ReportTask 和完整产品档案。"""
    sections_str = "、".join(task.sections) if task.sections else "（自主决定）"
    audience = task.target_audience or "产品团队"

    return (
        f"## 报告任务（ReportTask）\n"
        f"- 分析对象：{task.target_product}\n"
        f"- 竞品：{', '.join(task.competitors)}\n"
        f"- 目标读者：{audience}\n"
        f"- 章节顺序：{sections_str}\n"
        f"- 输出格式：{task.output_formats}\n"
        f"- 调用豆包终审：{task.invoke_call_report_reviewer}\n\n"
        f"## 产品档案数据\n"
        f"```json\n{profiles_json}\n```"
    )


def _extract_final_md(messages: list) -> str:
    """从 render_pdf 工具调用参数中提取报告 Markdown，避免误取 Agent 末尾总结句。"""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc["name"] == "render_pdf":
                    return tc["args"].get("markdown_content", "")
    return ""


def _extract_pdf_path(messages: list) -> str | None:
    """从工具调用结果中找 render_pdf 返回的文件路径。"""
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "render_pdf":
            return msg.content.strip()
    return None


def _extract_agent_signals(messages: list) -> list[dict]:
    """收集 reject_report_task 工具调用产出的 AgentSignal。"""
    return [
        json.loads(msg.content)
        for msg in messages
        if isinstance(msg, ToolMessage) and msg.name == "reject_report_task"
    ]


def _extract_reviewer_result(messages: list) -> QAResult:
    """从工具调用结果中找 call_reviewer 返回并反序列化，未调用时返回默认通过。"""
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "call_reviewer":
            return QAResult.model_validate_json(msg.content)
    return QAResult(product_name="__report__", passed=True, note="reviewer 未被调用")


def report_node(state: CCAState) -> dict:
    """Report Agent 节点：整合上游产出，生成 MD + PDF 竞品分析报告。"""
    report_task = ReportTask(**state["report_task"])
    forced = _collect_forced_keys(state.get("review_state", []))
    profiles_json = _serialize_profiles(state.get("profiles", {}), forced)

    @tool
    def call_reviewer(report_md: str) -> str:
        """对已完成的报告调用豆包跨模型终审，检查图文一致性与事实可溯源性。

        仅在 render_pdf 调用完成后、且任务中 invoke_reviewer 为 true 时调用。
        """
        result = call_report_reviewer(report_md, json.loads(profiles_json))
        return result.model_dump_json()

    @tool
    def reject_report_task(
        claim: str,
        evidence: list[str],
        suggested_fix: str | None = None,
        requires_debate: bool = False,
    ) -> str:
        """发现 ReportTask 存在错误或与档案数据矛盾时调用，向 PM 发出反驳信号。

        适用场景：
        - 竞品名单中的产品在档案中完全缺失（事实性，requires_debate=False）
        - 指定章节与现有数据严重不符，无法支撑（事实性，requires_debate=False）
        - 对目标产品定位或竞品选取有主观分歧（requires_debate=True，触发跨家族辩论）

        参数：
        - claim：问题/挑战的核心陈述，一句话讲清"哪里不对"
        - evidence：支撑 claim 的事实/观测/数据点列表，至少 1 条；事实性信号填观测数据，
          主观信号填支撑判断的依据
        - suggested_fix：可选，建议的修订方向
        - requires_debate：True 触发 PM 跨家族辩论；False 走 reroute 事实性纠错

        调用后继续按现有数据尽力完成报告；PM 收到信号后会修正任务并重新下发。
        """
        from datetime import datetime, timezone
        signal = AgentSignal(
            from_agent="report",
            kind="pm_challenge",
            target="report_task",
            payload=ChallengePayload(
                claim=claim,
                evidence=evidence,
                suggested_fix=suggested_fix,
            ),
            requires_debate=requires_debate,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        return signal.model_dump_json()

    agent = create_react_agent(
        model=gpt,
        tools=[render_chart, render_bar_chart, render_pdf, call_reviewer, reject_report_task],
    )

    result = agent.invoke({
        "messages": [
            SystemMessage(content=_load_system_prompt()),
            HumanMessage(content=_build_initial_message(report_task, profiles_json)),
        ]
    })

    messages = result["messages"]
    report_md = _extract_final_md(messages)
    pdf_path = _extract_pdf_path(messages)
    reviewer_result = _extract_reviewer_result(messages)
    signals = _extract_agent_signals(messages)

    if not report_task.invoke_call_report_reviewer:
        report_status = "unreviewed"
    elif reviewer_result.passed:
        report_status = "passed"
    else:
        report_status = "failed"

    return {
        "report_md": report_md,
        "report_pdf_path": pdf_path,
        "report_status": report_status,
        "qa_results": [reviewer_result.model_dump()],
        "agent_signals": signals,
        "audit_log": [{
            "agent": "report",
            "event": "report_generated",
            "status": report_status,
            "pdf_path": pdf_path,
            "signals_raised": len(signals),
        }],
    }
