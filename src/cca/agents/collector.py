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
from cca.schema import CollectTask
from cca.state import CCAState
from cca.tools.collector_tools import (
    challenge_pm,
    finalize_exploration,
    finalize_profile,
    request_product_replacement,
)
from cca.tools.fetcher import fetch_url
from cca.tools.search import web_search

_EXPLORATION_PROMPT_PATH = (
    Path(__file__).parent.parent / "prompts" / "collector_exploration.md"
)
_COLLECT_PROMPT_PATH = (
    Path(__file__).parent.parent / "prompts" / "collector_collect.md"
)


def _load_exploration_prompt() -> str:
    return _EXPLORATION_PROMPT_PATH.read_text(encoding="utf-8")


def _load_collect_prompt() -> str:
    return _COLLECT_PROMPT_PATH.read_text(encoding="utf-8")


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


# ── Phase 2：单产品深采集 ────────────────────────────────────────────


def _extract_finalized_profile(messages: list) -> dict | None:
    """从 finalize_profile 工具调用结果取最后一次提交。"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "finalize_profile":
            data = json.loads(msg.content)
            return data.get("profile")
    return None


def _extract_replacement_signals(messages: list) -> list[dict]:
    """提取 request_product_replacement 工具调用产出的 AgentSignal。"""
    return [
        json.loads(msg.content)
        for msg in messages
        if isinstance(msg, ToolMessage) and msg.name == "request_product_replacement"
    ]


def _build_collect_prompt_payload(task: CollectTask, context: dict) -> str:
    """组装单产品 ReAct 的 human message —— 包含 task + 上游 hint。"""
    payload: dict = {
        "task": task.model_dump(),
        "target_product": context.get("target_product"),
    }
    if context.get("domain_seed"):
        ds = context["domain_seed"]
        payload["domain_seed_hint"] = {
            "product_type_hint": ds.get("product_type_hint"),
            "terminology": ds.get("terminology", {}),
        }
    if context.get("product_brief"):
        payload["product_brief"] = context["product_brief"]
    return (
        f"## CollectTask · {task.product_name}\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"完成深采集后**必须**调用 `finalize_profile` 一次提交结构化 ProductProfile；"
        f"若数据完全采不到则调 `request_product_replacement` 申请换产品。"
        f"fetch_url 单产品上限 5 次，请谨慎挑页面。"
    )


def collect_one_product(task: CollectTask, context: dict) -> dict:
    """单产品 collection ReAct loop。

    设计为 LangGraph Send target 友好：context 携带跑这个产品所需的 state 切片
    （target_product / domain_seed / product_brief），不依赖完整 CCAState。

    返回 state 更新片段：
    - profile 成功：{"profiles": {name: ProductProfile dict}, "audit_log": [...]}
    - 申请换产品：{"agent_signals": [...], "audit_log": [...]}
    - finalize 未调（异常）：仅 audit_log 记 collect_failed
    """
    agent = create_react_agent(
        model=deepseek,
        tools=[web_search, fetch_url, finalize_profile, request_product_replacement],
    )
    result = agent.invoke({
        "messages": [
            SystemMessage(content=_load_collect_prompt()),
            HumanMessage(content=_build_collect_prompt_payload(task, context)),
        ]
    })

    messages = result["messages"]
    profile = _extract_finalized_profile(messages)
    signals = _extract_replacement_signals(messages)

    if profile is not None:
        return {
            "profiles": {task.product_name: profile},
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector",
                "event": "collect_done",
                "product_name": task.product_name,
                "dimensions_count": len(profile.get("dimensions", [])),
                "signals_raised": len(signals),
            }],
        }

    if signals:
        return {
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector",
                "event": "collect_replacement_requested",
                "product_name": task.product_name,
                "signals_raised": len(signals),
            }],
        }

    # finalize_profile 和 request_product_replacement 都没调 —— ReAct 异常退出
    return {
        "audit_log": [{
            "agent": "collector",
            "event": "collect_failed",
            "product_name": task.product_name,
            "reason": "ReAct 既未 finalize_profile 也未 request_product_replacement",
            "messages_count": len(messages),
        }],
    }


def _build_per_product_context(state: CCAState, product_name: str) -> dict:
    """从 state 抽出跑单产品所需的最小切片。"""
    exploration = state.get("exploration_result") or {}
    product_brief: dict | None = None
    for brief in exploration.get("initial_profiles", []):
        if brief.get("product_name") == product_name:
            product_brief = brief
            break
    return {
        "target_product": state["target_product"],
        "domain_seed": state.get("domain_seed"),
        "product_brief": product_brief,
    }


def collect_node(state: CCAState) -> dict:
    """Collector phase 2 同步顺序版：遍历 task_plan.collect_tasks 逐个调 collect_one_product。

    设计用途：
    - 单元测试和 demo 脚本的稳定入口
    - graph 接入前的 smoke test 路径

    LangGraph 接入后请改用 collect_dispatch_node（见下方 TODO）实现并行 fanout。
    """
    task_plan = state.get("task_plan") or {}
    raw_tasks = task_plan.get("collect_tasks", [])
    if not raw_tasks:
        return {
            "audit_log": [{
                "agent": "collector",
                "event": "collect_skipped",
                "reason": "task_plan.collect_tasks 为空",
            }],
        }

    profiles_acc: dict[str, dict] = {}
    signals_acc: list[dict] = []
    audit_acc: list[dict] = []

    for raw in raw_tasks:
        task = CollectTask(**raw) if isinstance(raw, dict) else raw
        context = _build_per_product_context(state, task.product_name)
        partial = collect_one_product(task, context)
        # list 字段累加，profiles dict 合并（同 key 后写覆盖；并发场景由 _merge_profiles 处理）
        for name, profile in (partial.get("profiles") or {}).items():
            profiles_acc[name] = profile
        signals_acc.extend(partial.get("agent_signals", []) or [])
        audit_acc.extend(partial.get("audit_log", []) or [])

    updates: dict = {"audit_log": audit_acc}
    if profiles_acc:
        updates["profiles"] = profiles_acc
    if signals_acc:
        updates["agent_signals"] = signals_acc
    return updates


# TODO(graph-integration)：LangGraph Send fanout dispatcher
# 接入 LangGraph 时把 collect_node 替换为：
#   def collect_dispatch_node(state):
#       from langgraph.types import Send
#       tasks = state["task_plan"]["collect_tasks"]
#       return [
#           Send("collect_one_product", {
#               "task": t,
#               "context": _build_per_product_context(state, t["product_name"]),
#           }) for t in tasks
#       ]
# 配合 collect_one_product 包装为 Send target 节点（payload 接收 task + context）。
# 当前 demo 仍用 collect_node 顺序跑，graph 接入后切换。
