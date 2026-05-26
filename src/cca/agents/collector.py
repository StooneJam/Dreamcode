"""Collector Agent —— 两阶段 ReAct 联网探索。

Phase 1: exploration_node
    输入: state.user_query + state.initial_brief + （可选）state.domain_seed
    输出: state.exploration_result (CollectorExplorationResult) + competitor_names
    工具: web_search / fetch_url / finalize_exploration / challenge_pm

Phase 2: collect_node (TODO，由 PM TaskPlan 触发后下发 CollectTask)

D-032 修订版后的输入约定：
- 若 state.domain_seed 非空（用户上传过文档，PM 在 phase 1 已蒸馏出 hint），
  Collector **优先采用** domain_seed.dimension_candidates / competitor_mentions 作为
  起点，再通过 web_search / fetch_url **联网验证 + 补充**。不再是"只能联网查找"。
- 若 state.domain_seed 为 None（用户没上传文档），Collector 走纯联网发现路径。

按 D-031，Collector 直接写自己 owner 的 state 字段（exploration_result / competitor_names）；
PM 通过阶段二 TaskPlan 消费或通过 debate 事后修正。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.llm.factory import deepseek
from cca.state import CCAState
from cca.tools.collector_tools import challenge_pm, finalize_exploration
from cca.tools.fetcher import fetch_url
from cca.tools.search import web_search

_EXPLORATION_PROMPT_PATH = (
    Path(__file__).parent.parent / "prompts" / "collector_exploration.md"
)


def _load_exploration_prompt() -> str:
    return _EXPLORATION_PROMPT_PATH.read_text(encoding="utf-8")


def _extract_exploration(messages: list) -> dict | None:
    """从 finalize_exploration 工具调用结果中提取 CollectorExplorationResult dict。

    取最后一次调用——LLM 偶尔会多次 finalize，以最新一次为准。
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "finalize_exploration":
            return json.loads(msg.content)
    return None


def _extract_signals(messages: list) -> list[dict]:
    """提取 challenge_pm 工具调用产出的 AgentSignal 列表。"""
    return [
        json.loads(msg.content)
        for msg in messages
        if isinstance(msg, ToolMessage) and msg.name == "challenge_pm"
    ]


def exploration_node(state: CCAState) -> dict:
    """Collector phase 1：粗探索目标产品的竞品 + 维度。

    输入有 state.domain_seed 时（用户上传过文档），优先采用其中的 dimension_candidates /
    competitor_mentions 作为起点，再联网验证补充；否则走纯联网发现路径。
    """
    brief = state.get("initial_brief") or {}
    target_product = brief.get("target_product") or state["target_product"]
    company_hint = brief.get("company_hint")
    user_query = state["user_query"]
    domain_seed = state.get("domain_seed")

    initial_msg = (
        f"## 任务：粗探索 {target_product} 的主要竞品与对比维度\n\n"
        f"- target_product: {target_product}\n"
        f"- company_hint（PM 训练知识 hint，需要你联网验证）: {company_hint or '（无）'}\n"
        f"- user_query: {user_query}\n"
    )
    if domain_seed:
        seed_hint = json.dumps(
            {
                "dimension_candidates": domain_seed.get("dimension_candidates", []),
                "competitor_mentions": domain_seed.get("competitor_mentions", []),
                "product_type_hint": domain_seed.get("product_type_hint"),
            },
            ensure_ascii=False,
        )
        initial_msg += (
            f"\n## PM 从用户上传文档蒸馏的 hint（优先采用，但仍需联网验证）\n"
            f"```json\n{seed_hint}\n```\n"
        )
    initial_msg += (
        "\n完成探索后**必须调用 `finalize_exploration` 工具一次**提交结构化结论。"
    )

    agent = create_react_agent(
        model=deepseek,
        tools=[web_search, fetch_url, finalize_exploration, challenge_pm],
    )
    result = agent.invoke({
        "messages": [
            SystemMessage(content=_load_exploration_prompt()),
            HumanMessage(content=initial_msg),
        ]
    })

    messages = result["messages"]
    exploration = _extract_exploration(messages)
    signals = _extract_signals(messages)

    if exploration is None:
        # ReAct 没调 finalize → 拿不到结构化结果，只保留 signals + audit
        return {
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector",
                "event": "exploration_failed",
                "reason": "未调用 finalize_exploration 工具",
                "messages_count": len(messages),
                "signals_raised": len(signals),
            }],
        }

    return {
        "exploration_result": exploration,
        "competitor_names": exploration["competitor_names"],
        "agent_signals": signals,
        "audit_log": [{
            "agent": "collector",
            "event": "exploration_done",
            "competitor_count": len(exploration["competitor_names"]),
            "signals_raised": len(signals),
        }],
    }
