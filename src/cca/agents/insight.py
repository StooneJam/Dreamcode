"""Insight Agent —— 问卷调查 + 评论采集 + NLP 情感分析，填充 profiles.sentiment。

架构位置：Phase 1（与 Collector 第二轮并发），等待 PM TaskPlan 下发后启动。
NLP 策略：NMF 主题提取（短文本效果优于 LDA）+ BERT/LLM 情感评分（config 可切换）。

BERT 模型选择：
  - 默认使用 config.nlp.bert_model 指定的预训练模型（开箱即用，无需额外准备）
  - 若已离线运行 scripts/finetune_bert.py 且 fine_tune.enabled=true，
    自动切换到本地微调模型（见 tools/insight_tools._effective_bert_model）
  - 微调是纯离线操作，不在 Agent 请求路径内执行
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

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


def _extract_sentiments(messages: list) -> dict[str, dict]:
    """从 finalize_sentiment 工具调用结果中提取各产品的 UserSentiment。"""
    results: dict[str, dict] = {}
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "finalize_sentiment":
            data = json.loads(msg.content)
            results[data["product_name"]] = data["sentiment"]
    return results


def _extract_signals(messages: list) -> list[dict]:
    """提取 challenge_pm 工具调用产出的 AgentSignal。"""
    return [
        json.loads(msg.content)
        for msg in messages
        if isinstance(msg, ToolMessage) and msg.name == "challenge_pm"
    ]


def insight_node(state: CCAState) -> dict:
    """Insight Agent 节点：为每个产品收集评论并输出 UserSentiment。"""
    if not state.get("task_plan"):
        return {"audit_log": [{"agent": "insight", "event": "skipped", "reason": "task_plan not set"}]}

    task_plan = TaskPlan(**state["task_plan"])
    profiles = state.get("profiles", {})
    cfg_nlp = load_config().get("nlp", {})
    sentiment_model = cfg_nlp.get("sentiment_model", "llm")

    tasks_json = json.dumps(
        [t.model_dump() for t in task_plan.insight_tasks],
        ensure_ascii=False,
    )
    profiles_hint = json.dumps(
        {name: {"product_type": p.get("product_type"), "website": p.get("website")}
         for name, p in profiles.items()},
        ensure_ascii=False,
    )
    sentiment_hint = (
        "情感分析请优先使用 analyze_sentiment_bert 工具（BERT 三分类），"
        "再对各情感组调用 extract_topics 提取主题。"
        if sentiment_model == "bert"
        else "情感分析请综合问卷回答和网络评论，直接用 LLM 判断正负面主题。"
    )

    agent = create_react_agent(
        model=deepseek,
        tools=[scrape_app_store, web_search, run_questionnaire, extract_topics,
               analyze_sentiment_bert, finalize_sentiment, challenge_pm],
    )
    result = agent.invoke({
        "messages": [
            SystemMessage(content=_load_prompt()),
            HumanMessage(content=(
                f"## InsightTask 列表\n```json\n{tasks_json}\n```\n\n"
                f"## 已知产品基本信息（来自 Collector）\n```json\n{profiles_hint}\n```\n\n"
                f"## 情感分析策略\n{sentiment_hint}\n\n"
                "请依次完成每个产品的情感分析，最终对每个产品调用 finalize_sentiment。"
            )),
        ]
    })

    messages = result["messages"]
    sentiments = _extract_sentiments(messages)
    signals = _extract_signals(messages)

    # 将 sentiment 合并回已有 profiles（不覆盖 Collector 写入的其他字段）
    updated_profiles = {
        name: {**profile, "sentiment": sentiments[name]} if name in sentiments else profile
        for name, profile in profiles.items()
    }

    return {
        "profiles": updated_profiles,
        "agent_signals": signals,
        "audit_log": [{
            "agent": "insight",
            "event": "sentiment_analyzed",
            "products": list(sentiments.keys()),
            "signals_raised": len(signals),
        }],
    }
