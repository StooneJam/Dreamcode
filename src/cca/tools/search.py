"""Tavily 联网搜索 —— PM 粗搜索 + Collector 细搜索共用入口。"""
from __future__ import annotations
import os
from tavily import TavilyClient


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """单次 Tavily 检索。
    Returns:
        list of {title, url, content}；查不到返空列表。
    """
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    response = client.search(query, max_results=max_results)
    return response.get("results", [])
