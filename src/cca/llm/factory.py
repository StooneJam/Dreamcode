"""三个模型家族的客户端统一入口。

Agent 直接 import 所需客户端，不在 Agent 内部实例化：
    from src.cca.llm.factory import gpt, deepseek, doubao
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(override=True)

# GPT-5 —— PM Agent / Report Agent / Collector 多模态分支
gpt = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5"),
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=60,
    temperature=0.3,
)

# DeepSeek —— Collector 文本分支 / Insight Agent / Analyst Agent
deepseek = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    timeout=60,
    temperature=0.3,
)

