"""三个模型家族的客户端统一入口。

Agent 直接 import 模块常量；Debate skill 用 get_llm(family) 按家族动态派发。
所有 agent / skill 必须通过这里取 LLM，不允许节点内 ChatOpenAI(...)。
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from cca.schema import AgentFamily

load_dotenv(override=True)

# GPT-5 —— PM Agent / Report Agent / Collector 多模态分支 / debate 仲裁
gpt = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5"),
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=60,
    temperature=0.3,
)

# DeepSeek —— Collector 文本分支 / Insight / Analyst / debate 辩方
deepseek = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    timeout=60,
    temperature=0.3,
)

# Doubao（火山方舟 Ark）—— 报告终审 debate 辩方
doubao = ChatOpenAI(
    model=os.getenv("DOUBAO_MODEL", ""),
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    timeout=60,
    temperature=0.2,
)


def get_llm(family: AgentFamily) -> ChatOpenAI:
    """按家族名返回客户端。Debate skill 用这个动态派发。"""
    if family == "gpt-5":
        return gpt
    if family == "deepseek":
        return deepseek
    if family == "doubao":
        return doubao
    raise ValueError(f"未知 family: {family!r}")
