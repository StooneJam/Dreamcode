"""Collector Agent —— 两阶段 ReAct 联网采集。

Phase 1 exploration_node：粗探索竞品 + 维度候选；产 CollectorExplorationResult。
Phase 2 collect_one_product：单产品深采集；产 ProductProfile。

domain_seed 非空时 phase 1 优先采用其中的 dimension_candidates / competitor_mentions
作为起点，再联网验证补充；为空走纯联网发现路径。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.agents._streaming import stream_react
from cca.llm.factory import get_llm
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

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _extract_tool_jsons(messages: list, tool_name: str) -> list[dict]:
    """收集指定工具调用结果中可解的 JSON。空 content / 非 JSON 跳过。"""
    out = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == tool_name and msg.content:
            try:
                out.append(json.loads(msg.content))
            except json.JSONDecodeError:
                continue
    return out


def _last_tool_json(messages: list, tool_name: str) -> dict | None:
    """取指定工具最后一次成功调用的 JSON 结果。"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == tool_name and msg.content:
            try:
                return json.loads(msg.content)
            except json.JSONDecodeError:
                continue
    return None


# ── cache key 稳定切片 ────────────────────────────────────────────────
# 把"上游浮动 / 与 prompt 无关的字段"从 cache key 里挡掉，避免 replay miss 与
# 上游 schema 扩展时的无意污染。原则：cache_key 字段集 = prompt 实际输入集。

_BRIEF_CACHE_FIELDS = ("product_name", "company", "website", "product_type")


def _stable_domain_seed(seed: dict | None) -> dict | None:
    """剔除 domain_seed 中的运行时浮动字段（extracted_at 等），保留 LLM 可见内容。"""
    if not seed:
        return seed
    return {k: v for k, v in seed.items() if k != "extracted_at"}


def _stable_product_brief(brief: dict | None) -> dict | None:
    """只取 _build_collect_message 实际灌进 prompt 的稳定字段；
    未来扩 ProductBrief schema 时新字段不会无意污染 cache。"""
    if not brief:
        return brief
    return {k: brief.get(k) for k in _BRIEF_CACHE_FIELDS}


# ── Phase 1：exploration ──────────────────────────────────────────────


def _build_exploration_message(state: CCAState) -> str:
    brief = state.get("initial_brief") or {}
    target = brief.get("target_product") or state["target_product"]
    msg = (
        f"## 任务：粗探索 {target} 的主要竞品与对比维度\n\n"
        f"- target_product: {target}\n"
        f"- company_hint: {brief.get('company_hint') or '（无）'}\n"
        f"- user_query: {state['user_query']}\n"
    )
    if seed := state.get("domain_seed"):
        hint = json.dumps({
            "dimension_candidates": seed.get("dimension_candidates", []),
            "competitor_mentions": seed.get("competitor_mentions", []),
            "product_type_hint": seed.get("product_type_hint"),
        }, ensure_ascii=False)
        msg += f"\n## PM 从用户文档蒸馏的 hint（优先采用，仍需联网验证）\n```json\n{hint}\n```\n"
    msg += "\n完成探索后**必须调用 `finalize_exploration` 一次**提交结构化结论。"
    return msg


def exploration_node(state: CCAState) -> dict:
    """Phase 1：粗探索竞品 + 维度，产 CollectorExplorationResult + 可选 challenge 信号。"""
    agent = create_react_agent(
        model=get_llm("deepseek"),
        tools=[web_search, fetch_url, finalize_exploration, challenge_pm],
    )
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_prompt("collector_exploration.md")),
            HumanMessage(content=_build_exploration_message(state)),
        ],
        label="Collector·explore",
        recursion_limit=40,
        cache_node="collector.exploration",
        cache_key={
            "target_product": state["target_product"],
            "initial_brief": state.get("initial_brief"),
            "domain_seed": _stable_domain_seed(state.get("domain_seed")),
            "user_query": state["user_query"],
        },
    )
    exploration = _last_tool_json(messages, "finalize_exploration")
    signals = _extract_tool_jsons(messages, "challenge_pm")

    if exploration is None:
        return {
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector", "event": "exploration_failed",
                "reason": "未调用 finalize_exploration",
                "messages_count": len(messages),
                "signals_raised": len(signals),
            }],
        }

    return {
        "exploration_result": exploration,
        "competitor_names": exploration["competitor_names"],
        "agent_signals": signals,
        "audit_log": [{
            "agent": "collector", "event": "exploration_done",
            "competitor_count": len(exploration["competitor_names"]),
            "signals_raised": len(signals),
        }],
    }


# ── Phase 2：单产品深采集 ──────────────────────────────────────────────


def _extract_finalized_profile(messages: list) -> dict | None:
    """取 finalize_profile 最后一次成功提交的 profile（经 ToolMessage.artifact 回传）。"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "finalize_profile":
            artifact = getattr(msg, "artifact", None)
            if isinstance(artifact, dict) and artifact.get("profile"):
                return artifact["profile"]
    return None


def _build_collect_message(task: CollectTask, context: dict) -> str:
    payload: dict = {"task": task.model_dump(), "target_product": context.get("target_product")}
    if seed := context.get("domain_seed"):
        payload["domain_seed_hint"] = {
            "product_type_hint": seed.get("product_type_hint"),
            "terminology": seed.get("terminology", {}),
        }
    if brief := context.get("product_brief"):
        payload["product_brief"] = brief
    return (
        f"## CollectTask · {task.product_name}\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"完成深采集后**必须**调用 `finalize_profile` 一次提交结构化 ProductProfile；"
        f"若数据完全采不到则调 `request_product_replacement` 申请换产品。"
        f"fetch_url 单产品上限 5 次。"
    )


def collect_one_product(task: CollectTask, context: dict) -> dict:
    """单产品 ReAct 深采集。

    context 是 state 切片（target_product / domain_seed / product_brief），
    便于 LangGraph Send fanout 时按产品 dispatch。
    """
    agent = create_react_agent(
        model=get_llm("deepseek"),
        tools=[web_search, fetch_url, finalize_profile, request_product_replacement],
    )
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_prompt("collector_collect.md")),
            HumanMessage(content=_build_collect_message(task, context)),
        ],
        label=f"Collector·{task.product_name}",
        recursion_limit=60,
        cache_node="collector.collect",
        cache_key={
            "task": task.model_dump(),
            "target_product": context.get("target_product"),
            "domain_seed": _stable_domain_seed(context.get("domain_seed")),
            "product_brief": _stable_product_brief(context.get("product_brief")),
        },
    )
    profile = _extract_finalized_profile(messages)
    signals = _extract_tool_jsons(messages, "request_product_replacement")

    if profile is not None:
        return {
            "profiles": {task.product_name: profile},
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector", "event": "collect_done",
                "product_name": task.product_name,
                "dimensions_count": len(profile.get("dimensions", [])),
                "signals_raised": len(signals),
            }],
        }
    if signals:
        return {
            "agent_signals": signals,
            "audit_log": [{
                "agent": "collector", "event": "collect_replacement_requested",
                "product_name": task.product_name, "signals_raised": len(signals),
            }],
        }
    return {
        "audit_log": [{
            "agent": "collector", "event": "collect_failed",
            "product_name": task.product_name,
            "reason": "ReAct 既未 finalize_profile 也未 request_product_replacement",
            "messages_count": len(messages),
        }],
    }


def build_collect_context(state: CCAState, product_name: str) -> dict:
    """抽出跑单产品所需的最小 state 切片。"""
    exploration = state.get("exploration_result") or {}
    brief = next(
        (b for b in exploration.get("initial_profiles", []) if b.get("product_name") == product_name),
        None,
    )
    task_plan = state.get("task_plan") or {}
    return {
        "target_product": state["target_product"],
        "domain_seed": state.get("domain_seed"),
        "product_brief": brief,
        # 软引导：让 Collector 知道 PM 预设的 bucket，尽量覆盖；非强制（不再事后字面卡覆盖）
        "tentative_buckets": task_plan.get("tentative_buckets") or [],
    }


