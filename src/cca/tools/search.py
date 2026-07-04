"""
Tavily web search -- shared entry point for PM's rough search and Collector's fine-grained search.
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

# result trimming (cache-safe cost control): Tavily content stays in ReAct history
# and gets resent every round, so local truncation only shrinks each round's new
# material, leaves the cached prefix untouched, and costs zero extra LLM calls.
# Both knobs are env-tunable.
_MAX_RESULTS_CAP = int(os.getenv("WEB_SEARCH_MAX_RESULTS_CAP", "5"))
_MAX_RESULT_CONTENT = int(os.getenv("WEB_SEARCH_MAX_CONTENT", "600"))

# per-run Tavily key uploaded by the frontend; falls back to the project's own .env
# key when None. Same pattern as llm/factory.py's _run_creds: the key travels via a
# contextvar, never into state (state gets recorded in audit_log and subscribed to
# by the frontend stream, so putting a key there would leak it).
_run_tavily_key: ContextVar[str | None] = ContextVar("cca_run_tavily_key", default=None)


@contextmanager
def use_tavily_key(key: str | None) -> Iterator[None]:
    """The frontend wraps a single run with this, outside graph.invoke, to inject the user's uploaded Tavily key.

    Empty/None -> falls back to the project's own .env key. An invalid key should be
    caught by validate_tavily_key before the run starts so the user can re-upload;
    this function doesn't handle that case.
    """
    token = _run_tavily_key.set(key or None)
    try:
        yield
    finally:
        _run_tavily_key.reset(token)


def validate_tavily_key(key: str) -> str | None:
    """Send one minimal search to Tavily as a liveness check. Returns None if usable, else an error string for the frontend to prompt a re-upload."""
    try:
        TavilyClient(api_key=key).search("ping", max_results=1)
    except Exception as exc:
        return f"Tavily key 校验失败（{type(exc).__name__}: {exc}）"
    return None

# operational/transient failures: caught and returned as an error string, keeping
# the graph alive with ReAct degrading gracefully (D-035).
# auth/config failures (MissingAPIKeyError / InvalidAPIKeyError) are deliberately
# excluded here -- a missing/wrong key should raise loudly on the very first call,
# not get swallowed into a soft error that produces a report with zero web data
# (CLAUDE.md §1).
_TRANSIENT_SEARCH_ERRORS = (
    tavily_errors.UsageLimitExceededError,  # 432 quota/rate-limited
    tavily_errors.TimeoutError,             # request timed out
    tavily_errors.ForbiddenError,           # 403
    tavily_errors.BadRequestError,          # 400 (usually an invalid LLM query; returned as a string for it to self-correct)
    requests.RequestException,              # ConnectionError + the HTTPError(5xx) from raise_for_status
)


def _trim_result(result: dict) -> dict:
    """Keep only {title, url, content}; content is truncated to _MAX_RESULT_CONTENT chars."""
    content = result.get("content") or ""
    if len(content) > _MAX_RESULT_CONTENT:
        content = content[:_MAX_RESULT_CONTENT]
    return {"title": result.get("title"), "url": result.get("url"), "content": content}


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
    max_results = min(max_results, _MAX_RESULTS_CAP)
    try:
        response = client.search(query, max_results=max_results, timeout=30)
    except _TRANSIENT_SEARCH_ERRORS as e:
        return (
            f"web_search 暂不可用（{type(e).__name__}: {e}）。"
            f"不要重试本次查询；请基于已采集到的信息继续，或对已知 URL 调 fetch_url 直接抓取。"
        )
    return [_trim_result(r) for r in response.get("results", [])]
