"""
Tavily 联网搜索 —— PM 粗搜索 + Collector 细搜索共用入口。
"""

from __future__ import annotations
import os
from langchain_core.tools import tool
from tavily import TavilyClient


@tool
def web_search(query: str, max_results: int = 5) -> list[dict]:
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
    response = client.search(query, max_results=max_results)
    return response.get("results", [])
