"""Unified client entry point for the three model families.

Agents/skills must always call get_llm(family) / get_report_llm() inside the node --
never import a module-level constant directly, or frontend-injected per-run
credentials won't take effect.

Two credential paths:
    no run creds (offline demo / tests): uses the .env singleton, behavior unchanged.
    run creds present (frontend-injected): builds a client from the user's uploaded
        endpoint (cached).

family is a "role slot", not a provider: gpt-5/deepseek/doubao are the planning /
execution / arbiter roles respectively. When a user uploads credentials, each slot
can hold any provider (OpenAI / Qwen / GLM ...); filling the three slots with
distinct providers is what gives cross-family bias isolation. cross_family_enabled()
returns False when fewer than 2 distinct endpoints are set, and the layer above
skips debate / call_report_reviewer.

Dev override (`CCA_DEV_MODEL_OVERRIDE=doubao`): only affects the .env path, pointing
all clients at Doubao.
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

# per-call LLM timeout (seconds). Collector/Insight's ReAct context grows in later
# rounds, and DeepSeek's peak-hour latency can spike too; 180s+ gives headroom,
# tune per-family via env vars if needed.
_GPT_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "600"))
_DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "600"))
_DOUBAO_TIMEOUT = int(os.getenv("DOUBAO_TIMEOUT", "600"))

# network-layer retry per LLM call. 1 retry = worst case 2x timeout;
# raising this makes a whole job hang longer -- on Railway, fail fast and let the user re-run.
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

_DEV_OVERRIDE = (os.getenv("CCA_DEV_MODEL_OVERRIDE") or "").lower()

# public flag -- business code (e.g. the debate skill) picks its LLM API path from this:
# Doubao doesn't support response_format=json_object, so under dev override all
# structured output must go through function_calling. The normal three-family path
# keeps json_mode / response_format=json_object (DeepSeek/GPT-5 tolerate it better).
DEV_DOUBAO_OVERRIDE: bool = _DEV_OVERRIDE == "doubao"

_DOUBAO_MAX_TOKENS = int(os.getenv("DOUBAO_MAX_TOKENS", "32768"))

_DOUBAO_THINKING = (os.getenv("DOUBAO_THINKING", "disabled") or "").lower()

# default temperature per role slot. Reused by the creds path when building clients, to stay consistent with the .env singletons.
_FAMILY_TEMP: dict[AgentFamily, float] = {"gpt-5": 0.2, "deepseek": 0.3, "doubao": 0.2}
_REPORT_TEMP = 0.8

# fallback priority for a missing family (when the user only fills 1-2 slots, an empty slot borrows from whichever of these is filled)
_FALLBACK_ORDER: tuple[AgentFamily, ...] = ("gpt-5", "deepseek", "doubao")


class LLMCredential(BaseModel):
    """The endpoint a user uploaded for a single role slot. base_url=None uses the provider's default."""

    api_key: str
    base_url: str | None = None
    model: str


# fixed defaults for the three slots, used by the server layer when building an
# LLMCredential from a slot name + the user's api_key.
SLOT_DEFAULTS: dict[AgentFamily, dict] = {
    "gpt-5":     {"model": "gpt-5",                       "base_url": None},
    "deepseek": {"model": "deepseek-v4-pro",             "base_url": "https://api.deepseek.com"},
    "doubao":   {"model": "ep-20260514111325-xjmj7",     "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
}


def _make_doubao(temperature: float, *, no_thinking: bool = False) -> ChatOpenAI:
    """Build a Doubao client. Under dev override, all three families use this.

    no_thinking=True forces the thinking param to be omitted (for tool_choice compatibility).
    Doubao API constraint: any thinking key in extra_body disables tool_choice support.
    """
    thinking_type = "disabled" if no_thinking else _DOUBAO_THINKING
    extra: dict = {}
    # when disabled, don't pass extra_body at all, to avoid conflicting with tool_choice; only pass it when explicitly enabled
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
    # under dev override, every agent (including ReAct tool calls) goes through Doubao.
    # thinking mode is incompatible with tool_choice, so it's force-disabled to keep the ReAct loop working.
    print(
        "[factory] DEV OVERRIDE active: all LLMs routed to Doubao; "
        "unset CCA_DEV_MODEL_OVERRIDE once things stabilize to switch back.",
        flush=True,
    )
    gpt = _make_doubao(temperature=0.2, no_thinking=True)
    deepseek = _make_doubao(temperature=0.3, no_thinking=True)
    doubao = _make_doubao(temperature=0.2, no_thinking=True)
    report_llm = _make_doubao(temperature=0.8, no_thinking=True)
else:
    # dedicated GPT-5 client for the Report Agent. temperature=0.8 for better writing quality.
    report_llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=_GPT_TIMEOUT,
        temperature=0.8,
        max_retries=_MAX_RETRIES,
    )
    # GPT-5 -- PM Agent / Report Agent / debate debater
    # temperature=0.2: slightly low for planning stability, while keeping PM's
    # flexibility on judgment calls like competitor selection / dimension priority /
    # section organization. D-039 reverted the original temperature=0 (it killed
    # analytical creativity).
    gpt = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=_GPT_TIMEOUT,
        temperature=0.2,
        max_retries=_MAX_RETRIES,
    )

    # DeepSeek -- Collector / Insight ReAct / debate debater
    deepseek = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        timeout=_DEEPSEEK_TIMEOUT,
        temperature=0.3,
        max_retries=_MAX_RETRIES,
        extra_body={"thinking": {"type": "disabled"}},
    )

    # Doubao (Volcengine Ark) -- debate judge / report final review
    doubao = _make_doubao(temperature=0.2)


# role -> singleton mapping for the offline .env path. Returned when creds are absent.
_ENV_CLIENTS: dict[AgentFamily, ChatOpenAI] = {
    "gpt-5": gpt,
    "deepseek": deepseek,
    "doubao": doubao,
}


# ── per-run credential injection ───────────────────────────────────────

_run_creds: ContextVar[dict[AgentFamily, LLMCredential] | None] = ContextVar(
    "cca_run_creds", default=None
)

# clients are reused within a run for the same endpoint set, to avoid rebuilding an httpx connection pool on every get_llm call.
_creds_client_cache: dict[tuple[str, str | None, str, float], ChatOpenAI] = {}


@contextmanager
def use_credentials(creds: dict[AgentFamily, LLMCredential] | None) -> Iterator[None]:
    """The frontend wraps a single run with this, outside graph.invoke, to inject the
    user's uploaded endpoint.

    creds empty/None -> falls back to the .env path (offline demo).
    """
    token = _run_creds.set(creds or None)
    try:
        yield
    finally:
        _run_creds.reset(token)


def _resolve_cred(
    creds: dict[AgentFamily, LLMCredential], family: AgentFamily
) -> LLMCredential:
    """An empty slot borrows a filled endpoint per _FALLBACK_ORDER."""
    if family in creds:
        return creds[family]
    for candidate in _FALLBACK_ORDER:
        if candidate in creds:
            return creds[candidate]
    raise ValueError("run creds is empty, should never reach _resolve_cred")


def _is_doubao_endpoint(base_url: str | None) -> bool:
    return bool(base_url and ("volces.com" in base_url or "ark.cn-beijing" in base_url))


def _build_from_cred(cred: LLMCredential, temperature: float) -> ChatOpenAI:
    """Build a client from the user's endpoint (cached). Doubao endpoints get max_tokens/timeout applied automatically."""
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
    """Return the client for a role slot. Uses the user's endpoint if run creds are set, otherwise the .env singleton."""
    if family not in _ENV_CLIENTS:
        raise ValueError(f"unknown family: {family!r}")
    creds = _run_creds.get()
    if creds is None:
        return _ENV_CLIENTS[family]
    return _build_from_cred(_resolve_cred(creds, family), _FAMILY_TEMP[family])


def get_report_llm() -> ChatOpenAI:
    """Reporter's dedicated client (gpt-5 slot, temperature=0.8)."""
    creds = _run_creds.get()
    if creds is None:
        return report_llm
    return _build_from_cred(_resolve_cred(creds, "gpt-5"), _REPORT_TEMP)


def cross_family_enabled() -> bool:
    """Whether cross-family review is on: only when the user has filled >=2 distinct endpoints.

    Always True on the offline .env path (all three families present, unchanged behavior).
    """
    creds = _run_creds.get()
    if creds is None:
        return True
    distinct = {(c.api_key, c.base_url, c.model) for c in creds.values()}
    return len(distinct) >= 2


# ── credential validation (called by the frontend on upload) ───────────


class CredentialCheck(BaseModel):
    family: AgentFamily
    ok: bool
    error: str | None = None


def validate_credentials(creds: dict[AgentFamily, LLMCredential]) -> list[CredentialCheck]:
    """Send a real minimal ping to each uploaded endpoint, returning a per-slot result. Never raises."""
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
