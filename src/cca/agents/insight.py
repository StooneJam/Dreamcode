"""Insight Agent —— 问卷 + 评论采集 + 情感分析，写 profiles.sentiment。

与 Collector phase 2 并发。情感正负面判定与主题归纳都由 LLM 基于采集到的评论直接完成。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.agents._streaming import stream_react
from cca.llm.factory import get_llm
from cca.schema import InsightTask
from cca.state import CCAState
from cca.tools.appstore import scrape_app_store
from cca.tools.insight_tools import (
    challenge_pm,
    finalize_sentiment,
    record_key_events,
    run_questionnaire,
)
from cca.tools.places import scrape_local_life
from cca.tools.review_channel import resolve_review_channel
from cca.tools.search import web_search

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "insight.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _extract_tool_jsons(messages: list, tool_name: str) -> list[dict]:
    """收集指定工具调用中可解的 JSON。"""
    out = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == tool_name and msg.content:
            try:
                out.append(json.loads(msg.content))
            except json.JSONDecodeError:
                continue
    return out


def _extract_sentiments(messages: list) -> dict[str, dict]:
    """finalize_sentiment 各次结果 → {product_name: sentiment}。"""
    results: dict[str, dict] = {}
    for data in _extract_tool_jsons(messages, "finalize_sentiment"):
        if "product_name" in data and "sentiment" in data:
            results[data["product_name"]] = data["sentiment"]
    return results


def _extract_events(messages: list) -> dict[str, list[dict]]:
    """record_key_events 各次结果 → {product_name: key_events}。"""
    results: dict[str, list[dict]] = {}
    for data in _extract_tool_jsons(messages, "record_key_events"):
        if "product_name" in data and "key_events" in data:
            results[data["product_name"]] = data["key_events"]
    return results


def _extract_signals(messages: list) -> list[dict]:
    return _extract_tool_jsons(messages, "challenge_pm")


def build_insight_context(state: CCAState, product_name: str) -> dict:
    """抽出单产品 insight 所需的最小 state 切片。"""
    task_plan = state.get("task_plan") or {}
    return {
        "profiles": state.get("profiles", {}),
        "competitor_names": state.get("competitor_names", []),
        "target_product": state["target_product"],
        # 数据源路由信号：一轮 debate 收敛的权威赛道，Insight 据此选 App Store / 电商 / 垂类
        "product_type": task_plan.get("product_type") or "",
        # 软引导：让 Insight 知道 PM 预设的 bucket，themes 尽量覆盖；非强制
        "tentative_buckets": task_plan.get("tentative_buckets") or [],
    }


def _build_insight_product_message(
    task: InsightTask, profiles: dict, competitor_names: list[str], product_type: str,
) -> str:
    task_json = json.dumps(task.model_dump(), ensure_ascii=False)
    profiles_hint = json.dumps(
        {n: {"product_type": p.get("product_type"), "website": p.get("website")}
         for n, p in profiles.items()},
        ensure_ascii=False,
    )
    sentiment_hint = (
        "情感分析直接由你完成：读采集到的评论，自行判定正负面并归纳正负面主题，"
        "无需调用任何分类工具。"
    )
    route = resolve_review_channel(product_type)
    platforms = "、".join(route.platforms) or "按该产品所在领域自行判断"
    if route.use_app_store:
        source_line = "本渠道用 scrape_app_store 抓评分+评论"
    elif route.channel == "local_life":
        source_line = (
            "本渠道先用 scrape_local_life(品牌) 取 Google Maps 聚合评分+评论数，"
            "再用 web_search 采上述平台评论文本供你判定情感"
        )
    else:
        source_line = "本渠道不抓 App Store，用 web_search 采集上述平台口碑"
    return (
        f"## InsightTask · {task.product_name}\n```json\n{task_json}\n```\n\n"
        f"## 数据源渠道（按 product_type 路由，target 与全部竞品统一用此渠道）\n"
        f"product_type: {product_type or '未知'}\n"
        f"评论抓取渠道: {route.label}\n"
        f"候选平台: {platforms}\n"
        f"{source_line}\n\n"
        f"## 竞品全列表（run_questionnaire 参数用）\n"
        f"{', '.join(competitor_names)}\n\n"
        f"## 已知产品基本信息（来自 Collector）\n```json\n{profiles_hint}\n```\n\n"
        f"## 情感分析策略\n{sentiment_hint}\n\n"
        f"请按上面分配的『评论抓取渠道』对 **{task.product_name}** 采集用户口碑与情感"
        f"（渠道路由依据见系统提示），完成后调用 finalize_sentiment。"
    )


def insight_one_product(task: InsightTask, context: dict) -> dict:
    """单产品 ReAct insight 分析。与 collect_one_product 签名一致，供 Send fanout 调用。

    context 需含 profiles / competitor_names / target_product。
    """
    profiles = context.get("profiles", {})
    competitor_names = context.get("competitor_names", [])
    product_type = context.get("product_type", "")

    agent = create_react_agent(
        model=get_llm("deepseek"),
        tools=[scrape_app_store, scrape_local_life, web_search, run_questionnaire,
               finalize_sentiment, record_key_events, challenge_pm],
    )
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_prompt()),
            HumanMessage(content=_build_insight_product_message(
                task, profiles, competitor_names, product_type,
            )),
        ],
        label=f"Insight·{task.product_name}",
        recursion_limit=30,
        # 不接 cache —— Insight 单产品 ReAct 耗时本就在可接受范围；
        # 且 cache_key 设计需要 worker 自治粒度切片（见讨论），暂不投资。
        # 流式打印仍然保留（stream_react 在 cache_key=None 时走纯真跑路径）。
    )
    sentiments = _extract_sentiments(messages)
    events = _extract_events(messages)
    signals = _extract_signals(messages)

    name = task.product_name
    result: dict = {}
    # Send fanout dispatch 时 context["profiles"] 是 task_plan 后的 snapshot（Collector 尚未跑完），
    # 所以**不能用 `name in profiles` 守卫** —— _merge_profiles reducer (D-031) 会自动按 key 合并字段，
    # Insight 写 {sentiment / key_events} 不论 Collector 是否已写过该产品都安全。
    profile_update: dict = {}
    if name in sentiments:
        profile_update["sentiment"] = sentiments[name]
    if name in events:
        profile_update["key_events"] = events[name]
    if profile_update:
        result["profiles"] = {name: profile_update}
    if signals:
        result["agent_signals"] = signals
    result["audit_log"] = [{
        "agent": "insight", "event": "sentiment_analyzed",
        "product": name,
        "sentiment_written": name in sentiments,
        "key_events_written": name in events,
        "signals_raised": len(signals),
    }]
    return result
