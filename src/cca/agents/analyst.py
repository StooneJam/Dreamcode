"""Analyst Agent —— 横向维度排序 + SWOT 分析，填充 profiles.swot。

Phase 2 完成（Collector + Insight QA 通过）后，PM 阶段三下发 AnalystTask，
本节点接管：
  1. 对 focus_dimensions 每个维度调 submit_dimension_ranking
  2. 对 product_names 每个产品调 finalize_swot
  3. 可通过 challenge_pm 向 PM 发出挑战信号

使用 DeepSeek 模型；输出只写 profiles.swot 增量（_merge_profiles reducer 合并）。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.llm.factory import deepseek
from cca.schema import AnalystTask
from cca.state import CCAState
from cca.tools.analyst_tools import challenge_pm, finalize_swot, submit_dimension_ranking

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analyst.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _slim_profile(profile: dict) -> dict:
    """保留分析所需字段，裁掉 sources / evidence URL 等大对象，控制 prompt 大小。"""
    dims = [
        {
            "name": d.get("name"),
            "category": d.get("category"),
            "facts": [{"statement": f.get("statement")} for f in d.get("facts", [])],
            "cross_product_note": d.get("cross_product_note"),
        }
        for d in profile.get("dimensions", [])
    ]
    return {
        "product_type": profile.get("product_type"),
        "target_users": profile.get("target_users"),
        "dimensions": dims,
        "pricing": profile.get("pricing"),
        "sentiment": {
            "appstore_cn_rating": (profile.get("sentiment") or {}).get("appstore_cn_rating"),
            "positive_themes": (profile.get("sentiment") or {}).get("positive_themes", []),
            "negative_themes": (profile.get("sentiment") or {}).get("negative_themes", []),
        } if profile.get("sentiment") else None,
    }


def _build_human_message(task: AnalystTask, profiles: dict) -> str:
    """组装 Analyst ReAct 的 human message。"""
    slim = {name: _slim_profile(p) for name, p in profiles.items()}
    payload = {"analyst_task": task.model_dump(), "profiles": slim}
    return (
        f"## AnalystTask\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        "请先对每个 focus_dimension 调用 submit_dimension_ranking，"
        "再对 product_names 中**每个产品**调用 finalize_swot 提交 SWOT。"
    )


def _extract_swots(messages: list) -> dict[str, dict]:
    """从 finalize_swot 工具调用结果提取各产品 SWOT，跳过空/非 JSON 条目。"""
    results: dict[str, dict] = {}
    for msg in messages:
        if not (isinstance(msg, ToolMessage) and msg.name == "finalize_swot"):
            continue
        if not msg.content:
            continue
        try:
            data = json.loads(msg.content)
        except json.JSONDecodeError:
            continue
        if "product_name" in data and "swot" in data:
            results[data["product_name"]] = data["swot"]
    return results


def _extract_rankings(messages: list) -> list[dict]:
    """从 submit_dimension_ranking 工具调用结果提取维度排名列表。"""
    results = []
    for msg in messages:
        if not (isinstance(msg, ToolMessage) and msg.name == "submit_dimension_ranking"):
            continue
        if not msg.content:
            continue
        try:
            results.append(json.loads(msg.content))
        except json.JSONDecodeError:
            continue
    return results


def _extract_signals(messages: list) -> list[dict]:
    """从 challenge_pm 工具调用结果提取 AgentSignal 列表。"""
    results = []
    for msg in messages:
        if not (isinstance(msg, ToolMessage) and msg.name == "challenge_pm"):
            continue
        if not msg.content:
            continue
        try:
            results.append(json.loads(msg.content))
        except json.JSONDecodeError:
            continue
    return results


def _build_output(swots: dict, rankings: list, signals: list) -> dict:
    """将提取结果组装为 state 更新片段。"""
    swot_updates = {name: {"swot": swot} for name, swot in swots.items()}
    ranking_audits = [
        {"agent": "analyst", "event": "dimension_ranked", **r}
        for r in rankings
    ]
    summary = {
        "agent": "analyst",
        "event": "analysis_done",
        "swot_products": list(swots.keys()),
        "rankings_count": len(rankings),
        "signals_raised": len(signals),
    }
    return {
        "profiles": swot_updates,
        "agent_signals": signals,
        "audit_log": ranking_audits + [summary],
    }


def analyst_node(state: CCAState) -> dict:
    """Analyst Agent 节点：维度横向排序 + SWOT 分析，填充 profiles.swot。"""
    if not state.get("analyst_task"):
        return {"audit_log": [{"agent": "analyst", "event": "skipped", "reason": "analyst_task not set"}]}

    task = AnalystTask(**state["analyst_task"])
    profiles = state.get("profiles", {})

    agent = create_react_agent(
        model=deepseek,
        tools=[submit_dimension_ranking, finalize_swot, challenge_pm],
    )
    result = agent.invoke(
        {
            "messages": [
                SystemMessage(content=_load_prompt()),
                HumanMessage(content=_build_human_message(task, profiles)),
            ]
        },
        config={"recursion_limit": 20},
    )

    messages = result["messages"]
    return _build_output(
        swots=_extract_swots(messages),
        rankings=_extract_rankings(messages),
        signals=_extract_signals(messages),
    )
