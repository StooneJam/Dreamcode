"""
Tavily 联网搜索 —— PM 粗搜索 + Collector 细搜索共用入口。
"""

from __future__ import annotations
import os

import requests
from langchain_core.tools import tool
from tavily import TavilyClient
from tavily import errors as tavily_errors

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
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    try:
        response = client.search(query, max_results=max_results)
    except _TRANSIENT_SEARCH_ERRORS as e:
        return (
            f"web_search 暂不可用（{type(e).__name__}: {e}）。"
            f"不要重试本次查询；请基于已采集到的信息继续，或对已知 URL 调 fetch_url 直接抓取。"
        )
    return response.get("results", [])
