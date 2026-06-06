"""三个模型家族的客户端统一入口。

Agent / skill 一律在节点内调 get_llm(family) / get_report_llm() 取 LLM，
不允许 import 模块常量抓死引用——否则前端注入的 per-run 凭证无法生效。

凭证两条路径：
    无 run creds（离线 demo / 测试）：走 .env 单例，行为与历史完全一致。
    有 run creds（前端注入）：按用户上传的 endpoint 现建客户端（带缓存）。

family 是“角色槽位”而非 provider：gpt-5/deepseek/doubao 分别是规划 / 执行 / 仲裁角色。
用户上传时每个槽位可放任意 provider（OpenAI / Qwen / GLM ...）；三槽填不同 provider
即满足跨家族 bias 隔离。distinct endpoint < 2 时 cross_family_enabled() 返回 False，
上层跳过 debate / call_report_reviewer。

dev override（`CCA_DEV_MODEL_OVERRIDE=doubao`）：仅作用于 .env 路径，把全部客户端指向豆包。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from cca.schema import AgentFamily

load_dotenv(override=True)

# 单次 LLM 调用超时（秒）。Collector / Insight ReAct 跑到后几轮 context 会膨胀，
# DeepSeek 高峰期延迟也可能上来；180s 给个宽余量，必要时按家族通过环境变量调。
_GPT_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "600"))
_DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "600"))
_DOUBAO_TIMEOUT = int(os.getenv("DOUBAO_TIMEOUT", "600"))

# 单次 LLM 调用网络层 retry。1 次重试 = 最坏情况 timeout × 2；
# 改大会让整个 job 挂更久，Railway 上宁可快速失败让用户重跑。
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

_DEV_OVERRIDE = (os.getenv("CCA_DEV_MODEL_OVERRIDE") or "").lower()

# 公开 flag —— 业务代码（如 debate skill）按此选 LLM API 路径：
# Doubao 不支持 response_format=json_object，dev override 时所有结构化输出都得走 function_calling。
# 三家族原路径下保留 json_mode / response_format=json_object（DeepSeek/GPT-5 容错更好）。
DEV_DOUBAO_OVERRIDE: bool = _DEV_OVERRIDE == "doubao"

_DOUBAO_MAX_TOKENS = int(os.getenv("DOUBAO_MAX_TOKENS", "32768"))

_DOUBAO_THINKING = (os.getenv("DOUBAO_THINKING", "disabled") or "").lower()

# 各角色槽位的默认 temperature。creds 路径建客户端时复用，保持与 .env 单例一致。
_FAMILY_TEMP: dict[AgentFamily, float] = {"gpt-5": 0.2, "deepseek": 0.3, "doubao": 0.2}
_REPORT_TEMP = 0.8

# 缺失家族的 fallback 优先级（用户只填 1-2 槽时，空槽借这个顺序里已填的）
_FALLBACK_ORDER: tuple[AgentFamily, ...] = ("gpt-5", "deepseek", "doubao")


class LLMCredential(BaseModel):
    """用户为单个角色槽位上传的 endpoint。base_url=None 用 provider 默认。"""

    api_key: str
    base_url: str | None = None
    model: str


# 三个槽位的固定默认值，服务器层按槽位名 + 用户 api_key 构造 LLMCredential 时使用。
SLOT_DEFAULTS: dict[AgentFamily, dict] = {
    "gpt-5":     {"model": "gpt-5",                       "base_url": None},
    "deepseek": {"model": "deepseek-v4-pro",             "base_url": "https://api.deepseek.com"},
    "doubao":   {"model": "ep-20260514111325-xjmj7",     "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
}


def _make_doubao(temperature: float, *, no_thinking: bool = False) -> ChatOpenAI:
    """构造一个 Doubao 客户端。dev override 时三个家族都用它。

    no_thinking=True 强制不传 thinking 参数（用于 tool_choice 兼容场景）。
    Doubao API 限制：extra_body 中带任何 thinking 键时，不支持 tool_choice。
    """
    thinking_type = "disabled" if no_thinking else _DOUBAO_THINKING
    extra: dict = {}
    # disabled 时不传 extra_body，避免与 tool_choice 冲突；只有明确启用时才传
    if thinking_type in ("enabled", "auto"):
        extra["extra_body"] = {"thinking": {"type": thinking_type}}
    return ChatOpenAI(
        model=os.getenv("DOUBAO_MODEL", SLOT_DEFAULTS["doubao"]["model"]),
        api_key=os.getenv("DOUBAO_API_KEY"),
        base_url=os.getenv("DOUBAO_BASE_URL", SLOT_DEFAULTS["doubao"]["base_url"]),
        timeout=_DOUBAO_TIMEOUT,
        temperature=temperature,
        max_retries=_MAX_RETRIES,
        max_tokens=_DOUBAO_MAX_TOKENS,
        **extra,
    )


if _DEV_OVERRIDE == "doubao":
    # dev override 下所有 agent（含 ReAct 工具调用）都走豆包。
    # 思考模式与 tool_choice 不兼容，强制关闭，保证 ReAct loop 正常运行。
    print(
        "[factory] DEV OVERRIDE active: 全部 LLM 走 Doubao；"
        "流程稳定后 unset CCA_DEV_MODEL_OVERRIDE 切回原配置。",
        flush=True,
    )
    gpt = _make_doubao(temperature=0.2, no_thinking=True)
    deepseek = _make_doubao(temperature=0.3, no_thinking=True)
    doubao = _make_doubao(temperature=0.2, no_thinking=True)
    report_llm = _make_doubao(temperature=0.8, no_thinking=True)
else:
    # Report Agent 专用 GPT-5 客户端。temperature=0.8 提升语言组织与表达质量。
    report_llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=_GPT_TIMEOUT,
        temperature=0.8,
        max_retries=_MAX_RETRIES,
    )
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


# 离线 .env 路径的角色 → 单例映射。creds 缺省时返回这些。
_ENV_CLIENTS: dict[AgentFamily, ChatOpenAI] = {
    "gpt-5": gpt,
    "deepseek": deepseek,
    "doubao": doubao,
}


# ── per-run 凭证注入 ────────────────────────────────────────────────────

_run_creds: ContextVar[dict[AgentFamily, LLMCredential] | None] = ContextVar(
    "cca_run_creds", default=None
)

# 同一组 endpoint 在一次运行里复用客户端，避免每次 get_llm 都新建 httpx 连接池。
_creds_client_cache: dict[tuple[str, str | None, str, float], ChatOpenAI] = {}


@contextmanager
def use_credentials(creds: dict[AgentFamily, LLMCredential] | None) -> Iterator[None]:
    """前端在 graph.invoke 外层用这个包住一次运行，注入用户上传的 endpoint。

    creds 为空 / None → 回落 .env 路径（离线 demo）。
    """
    token = _run_creds.set(creds or None)
    try:
        yield
    finally:
        _run_creds.reset(token)


def _resolve_cred(
    creds: dict[AgentFamily, LLMCredential], family: AgentFamily
) -> LLMCredential:
    """空槽按 _FALLBACK_ORDER 借已填的 endpoint。"""
    if family in creds:
        return creds[family]
    for candidate in _FALLBACK_ORDER:
        if candidate in creds:
            return creds[candidate]
    raise ValueError("run creds 为空，不应走到 _resolve_cred")


def _is_doubao_endpoint(base_url: str | None) -> bool:
    return bool(base_url and ("volces.com" in base_url or "ark.cn-beijing" in base_url))


def _build_from_cred(cred: LLMCredential, temperature: float) -> ChatOpenAI:
    """按用户 endpoint 现建客户端（缓存）。豆包 endpoint 自动应用 max_tokens 与超时。"""
    key = (cred.api_key, cred.base_url, cred.model, temperature)
    client = _creds_client_cache.get(key)
    if client is None:
        is_doubao = _is_doubao_endpoint(cred.base_url)
        kwargs: dict = dict(
            model=cred.model,
            api_key=cred.api_key,
            base_url=cred.base_url,
            timeout=_DOUBAO_TIMEOUT if is_doubao else _GPT_TIMEOUT,
            temperature=temperature,
            max_retries=_MAX_RETRIES,
        )
        if is_doubao:
            kwargs["max_tokens"] = _DOUBAO_MAX_TOKENS
        client = ChatOpenAI(**kwargs)
        _creds_client_cache[key] = client
    return client


def get_llm(family: AgentFamily) -> ChatOpenAI:
    """按角色槽位返回客户端。有 run creds 走用户 endpoint，否则 .env 单例。"""
    if family not in _ENV_CLIENTS:
        raise ValueError(f"未知 family: {family!r}")
    creds = _run_creds.get()
    if creds is None:
        return _ENV_CLIENTS[family]
    return _build_from_cred(_resolve_cred(creds, family), _FAMILY_TEMP[family])


def get_report_llm() -> ChatOpenAI:
    """Reporter 专用客户端（gpt-5 槽位，temperature=0.8）。"""
    creds = _run_creds.get()
    if creds is None:
        return report_llm
    return _build_from_cred(_resolve_cred(creds, "gpt-5"), _REPORT_TEMP)


def cross_family_enabled() -> bool:
    """跨家族审核是否启用：用户填 >=2 个不同 endpoint 才开。

    离线 .env 路径恒为 True（三家族齐全，行为不变）。
    """
    creds = _run_creds.get()
    if creds is None:
        return True
    distinct = {(c.api_key, c.base_url, c.model) for c in creds.values()}
    return len(distinct) >= 2


# ── 凭证校验（供前端上传时调用）────────────────────────────────────────


class CredentialCheck(BaseModel):
    family: AgentFamily
    ok: bool
    error: str | None = None


def validate_credentials(creds: dict[AgentFamily, LLMCredential]) -> list[CredentialCheck]:
    """对每个上传的 endpoint 真打一次最小 ping，返回逐槽结果。永不 raise。"""
    results: list[CredentialCheck] = []
    for family, cred in creds.items():
        client = ChatOpenAI(
            model=cred.model,
            api_key=cred.api_key,
            base_url=cred.base_url,
            timeout=30,
            max_retries=0,
            temperature=0,
        )
        try:
            client.invoke([HumanMessage(content="ping")])
            results.append(CredentialCheck(family=family, ok=True))
        except Exception as exc:
            results.append(CredentialCheck(family=family, ok=False, error=str(exc)))
    return results
