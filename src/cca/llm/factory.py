"""三个模型家族的客户端统一入口。

Agent 直接 import 模块常量；Debate skill 用 get_llm(family) 按家族动态派发。
所有 agent / skill 必须通过这里取 LLM，不允许节点内 ChatOpenAI(...)。

dev override（`CCA_DEV_MODEL_OVERRIDE=doubao`）：
    开发期豆包 API 可报销时，把 gpt / deepseek / doubao 三个客户端全部指向豆包。
    业务代码零改动；副作用：跨家族 debate 退化为同家族自审（bias 隔离失效，开发期可忍）。
    流程稳定后 unset 即可切回 GPT-5 + DeepSeek + Doubao 三家族原配置。
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

# 单次 LLM 调用网络层 retry。OpenAI SDK 内置 exponential backoff，
# 主要应对 Doubao Ark 在 Send fanout 并发下偶发的 TCP reset（WinError 10054）
# 与瞬时 TLS 握手失败。默认 2 次扛不住，调到 5。
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))

_DEV_OVERRIDE = (os.getenv("CCA_DEV_MODEL_OVERRIDE") or "").lower()

# 公开 flag —— 业务代码（如 debate skill）按此选 LLM API 路径：
# Doubao 不支持 response_format=json_object，dev override 时所有结构化输出都得走 function_calling。
# 三家族原路径下保留 json_mode / response_format=json_object（DeepSeek/GPT-5 容错更好）。
DEV_DOUBAO_OVERRIDE: bool = _DEV_OVERRIDE == "doubao"


def _make_doubao(temperature: float) -> ChatOpenAI:
    """构造一个 Doubao 客户端。dev override 时三个家族都用它。"""
    return ChatOpenAI(
        model=os.getenv("DOUBAO_MODEL", ""),
        api_key=os.getenv("DOUBAO_API_KEY"),
        base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        timeout=_DOUBAO_TIMEOUT,
        temperature=temperature,
        max_retries=_MAX_RETRIES,
    )


# Report Agent 专用 GPT-5 客户端，不受 dev override 影响。
# Reporter 是最终输出环节，工具调用遵从性要求高，始终走 GPT-5。
report_llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5"),
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=_GPT_TIMEOUT,
    temperature=0.2,
    max_retries=_MAX_RETRIES,
)

if _DEV_OVERRIDE == "doubao":
    # 开发期 PM / Collector / Insight 走豆包，Reporter 单独走 GPT-5（见 report_llm）。
    print(
        "[factory] DEV OVERRIDE active: PM/Collector/Insight 走 Doubao，"
        "Reporter 保持 GPT-5；流程稳定后 unset CCA_DEV_MODEL_OVERRIDE 切回原配置。",
        flush=True,
    )
    gpt = _make_doubao(temperature=0.2)
    deepseek = _make_doubao(temperature=0.3)
    doubao = _make_doubao(temperature=0.2)
else:
    # GPT-5 —— PM Agent / Report Agent / debate 辩方
    # temperature=0.2：稍偏低保证规划稳定性，同时保留 PM 在竞品选择 / 维度优先级 /
    # 章节组织等判断点上的灵活度。D-039 撤回原 temperature=0（扼杀分析创造性）。
    gpt = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=_GPT_TIMEOUT,
        temperature=0.2,
        max_retries=_MAX_RETRIES,
    )

    # DeepSeek —— Collector / Insight ReAct / debate 辩方
    deepseek = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        timeout=_DEEPSEEK_TIMEOUT,
        temperature=0.3,
        max_retries=_MAX_RETRIES,
        extra_body={"thinking": {"type": "disabled"}},
    )

    # Doubao（火山方舟 Ark）—— debate judge / report 终审
    doubao = _make_doubao(temperature=0.2)


def get_llm(family: AgentFamily) -> ChatOpenAI:
    """按家族名返回客户端。Debate skill 用这个动态派发。

    dev override 模式下三个 family 返回的都是 Doubao 客户端（同一三个实例，
    不是同一引用——保留各自 temperature 配置）。
    """
    if family == "gpt-5":
        return gpt
    if family == "deepseek":
        return deepseek
    if family == "doubao":
        return doubao
    raise ValueError(f"未知 family: {family!r}")
