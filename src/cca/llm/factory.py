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

# 单次 LLM 调用超时（秒）。Collector / Insight ReAct 跑到后几轮 context 会膨胀，
# DeepSeek 高峰期延迟也可能上来；180s 给个宽余量，必要时按家族通过环境变量调。
_GPT_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "180"))
_DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "180"))
_DOUBAO_TIMEOUT = int(os.getenv("DOUBAO_TIMEOUT", "120"))

# GPT-5 —— PM Agent / Report Agent / debate 辩方
# temperature=0：求 PM 三阶段输出确定性，让下游 cache key 稳定（D-036 + DP-006）
gpt = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5"),
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=_GPT_TIMEOUT,
    temperature=0,
)

# DeepSeek —— Collector / Insight ReAct / debate 辩方
deepseek = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    timeout=_DEEPSEEK_TIMEOUT,
    temperature=0.3,
    extra_body={"thinking": {"type": "disabled"}},
)

# Doubao（火山方舟 Ark）—— debate judge / report 终审
doubao = ChatOpenAI(
    model=os.getenv("DOUBAO_MODEL", ""),
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    timeout=_DOUBAO_TIMEOUT,
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
