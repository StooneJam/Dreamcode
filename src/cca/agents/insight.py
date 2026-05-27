"""Insight Agent —— 问卷 + 评论采集 + NLP 情感分析，写 profiles.sentiment。

与 Collector phase 2 并发。NMF 主题 + BERT/LLM 情感二选一（config.nlp.sentiment_model）。
若 fine_tune.enabled 且本地有微调模型，BERT 工具自动切换；微调脚本离线跑。
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.agents._streaming import stream_react
from cca.llm.factory import deepseek
from cca.schema import TaskPlan
from cca.settings import load_config
from cca.state import CCAState
from cca.tools.appstore import scrape_app_store
from cca.tools.insight_tools import (
    analyze_sentiment_bert,
    challenge_pm,
    extract_topics,
    finalize_sentiment,
    run_questionnaire,
)
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


def _extract_signals(messages: list) -> list[dict]:
    return _extract_tool_jsons(messages, "challenge_pm")


def _build_human_message(task_plan: TaskPlan, profiles: dict, sentiment_model: str) -> str:
    tasks_json = json.dumps([t.model_dump() for t in task_plan.insight_tasks], ensure_ascii=False)
    profiles_hint = json.dumps(
        {n: {"product_type": p.get("product_type"), "website": p.get("website")}
         for n, p in profiles.items()},
        ensure_ascii=False,
    )
    sentiment_hint = (
        "情感分析请优先使用 analyze_sentiment_bert（BERT 三分类），"
        "再对各情感组调 extract_topics 提取主题。"
        if sentiment_model == "bert"
        else "情感分析请综合问卷回答和网络评论，直接用 LLM 判断正负面主题。"
    )
    return (
        f"## InsightTask 列表\n```json\n{tasks_json}\n```\n\n"
        f"## 竞品列表（run_questionnaire 的 competitor_names 参数用这个）\n"
        f"{', '.join(task_plan.competitor_names)}\n\n"
        f"## 已知产品基本信息（来自 Collector）\n```json\n{profiles_hint}\n```\n\n"
        f"## 情感分析策略\n{sentiment_hint}\n\n"
        f"请依次完成每个产品，最终对每个产品调用 finalize_sentiment。"
    )


def insight_node(state: CCAState) -> dict:
    """为每个产品采集评论 + NLP 分析，输出 sentiment 增量到 profiles。"""
    if not state.get("task_plan"):
        return {"audit_log": [{"agent": "insight", "event": "skipped", "reason": "task_plan not set"}]}

    task_plan = TaskPlan(**state["task_plan"])
    profiles = state.get("profiles", {})
    sentiment_model = load_config().get("nlp", {}).get("sentiment_model", "llm")

    agent = create_react_agent(
        model=deepseek,
        tools=[scrape_app_store, web_search, run_questionnaire, extract_topics,
               analyze_sentiment_bert, finalize_sentiment, challenge_pm],
    )
    messages = stream_react(
        agent,
        [
            SystemMessage(content=_load_prompt()),
            HumanMessage(content=_build_human_message(task_plan, profiles, sentiment_model)),
        ],
        label="Insight",
        recursion_limit=50,
        cache_node="insight",
        cache_key={
            "competitor_names": task_plan.competitor_names,
            "insight_tasks": [t.model_dump() for t in task_plan.insight_tasks],
            "profile_names": sorted(profiles.keys()),
            "sentiment_model": sentiment_model,
        },
    )
    sentiments = _extract_sentiments(messages)
    signals = _extract_signals(messages)

    # 只返回 sentiment 增量，由 _merge_profiles reducer 合并；避免覆盖 Collector 已写字段
    sentiment_updates = {
        name: {"sentiment": sentiments[name]}
        for name in sentiments
        if name in profiles
    }
    return {
        "profiles": sentiment_updates,
        "agent_signals": signals,
        "audit_log": [{
            "agent": "insight", "event": "sentiment_analyzed",
            "products": list(sentiments.keys()),
            "signals_raised": len(signals),
        }],
    }
