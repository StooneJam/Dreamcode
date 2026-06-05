"""
Tavily 联网搜索 —— PM 粗搜索 + Collector 细搜索共用入口。
"""

from __future__ import annotations
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

import requests
from langchain_core.tools import tool
from tavily import TavilyClient
from tavily import errors as tavily_errors

# 前端上传的 per-run Tavily key；None 时回落 .env 里项目自己的 key。
# 与 llm/factory.py 的 _run_creds 同一范式：key 走 contextvar，不进 state（state 会被
# audit_log 记录、被前端 stream 订阅，密钥进 state 等于泄漏）。
_run_tavily_key: ContextVar[str | None] = ContextVar("cca_run_tavily_key", default=None)


@contextmanager
def use_tavily_key(key: str | None) -> Iterator[None]:
    """前端在 graph.invoke 外层包住一次运行，注入用户上传的 Tavily key。

    空 / None → 回落 .env 里项目自己的 key。非法 key 应在 run 入口前用
    validate_tavily_key 拦下让用户重传，不在这里兜底。
    """
    token = _run_tavily_key.set(key or None)
    try:
        yield
    finally:
        _run_tavily_key.reset(token)


def validate_tavily_key(key: str) -> str | None:
    """对 Tavily 打一次最小 search 探活。返回 None 表示可用，否则返回错误串供前端提示重传。"""
    try:
        TavilyClient(api_key=key).search("ping", max_results=1)
    except Exception as exc:
        return f"Tavily key 校验失败（{type(exc).__name__}: {exc}）"
    return None

# 运营/瞬时类失败：catch 返错误串，让图存活、ReAct 降级（D-035）。
# auth/config 类（MissingAPIKeyError / InvalidAPIKeyError）故意不在此列 ——
# 让 key 缺失/错误第一次调用就响亮 raise，而非吞成软错误产出零联网数据的报告（CLAUDE.md §1）。
_TRANSIENT_SEARCH_ERRORS = (
    tavily_errors.UsageLimitExceededError,  # 432 配额/限流
    tavily_errors.TimeoutError,             # 请求超时
    tavily_errors.ForbiddenError,           # 403
    tavily_errors.BadRequestError,          # 400（多为 LLM query 不合法，返串让其自修）
    requests.RequestException,              # ConnectionError + raise_for_status 的 HTTPError(5xx)
)


@tool
def web_search(query: str, max_results: int = 5) -> list[dict] | str:
    """
    Search the public web for fresh, factual information about a product, company, or competitor landscape.

    Call this tool when you need:
    - To discover competitors of a given product
    - To verify a company's official website / vendor / launch year
    - To find recent news, pricing, or feature comparisons
    - Any information not safely covered by your training knowledge

    Args:
        query: Natural-language search query in any language.
        max_results: Max results to return (1–10, default 5).

    Returns:
        List of {title, url, content}. Empty list if nothing found.
    """
    client = TavilyClient(api_key=_run_tavily_key.get() or os.getenv("TAVILY_API_KEY"))
    try:
        response = client.search(query, max_results=max_results, timeout=30)
    except _TRANSIENT_SEARCH_ERRORS as e:
        return (
            f"web_search 暂不可用（{type(e).__name__}: {e}）。"
            f"不要重试本次查询；请基于已采集到的信息继续，或对已知 URL 调 fetch_url 直接抓取。"
        )
    return response.get("results", [])
