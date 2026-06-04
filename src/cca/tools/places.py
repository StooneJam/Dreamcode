"""Google Places 结构化口碑取数 —— 本地生活渠道（大众点评/美团 类）的品牌级评分。

官方 Text Search API 直接返回每家门店的 rating + user_ratings_total，全球覆盖，
对出海竞品远好过高德/大众点评爬取。品牌级用 Top-N 加权平均聚合多家门店。
只回评分+评论数，不回评论正文——情感主题的评论文本仍走 web_search。
结果缓存进 store.db（复用 react_cache）防重复计费；key 缺失 fail-soft，LLM 自然降级。
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from cca.memory import react_cache

_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_TIMEOUT = 15.0
_TOP_N = 20


def _aggregate_rating(results: list[dict], top_n: int = _TOP_N) -> dict | None:
    """Top-N 加权平均：按评论数加权各门店星级。无可用门店返 None。"""
    usable = [
        (r["rating"], r["user_ratings_total"])
        for r in results
        if isinstance(r.get("rating"), (int, float))
        and isinstance(r.get("user_ratings_total"), int)
        and r["user_ratings_total"] > 0
    ]
    if not usable:
        return None
    usable.sort(key=lambda rc: rc[1], reverse=True)
    top = usable[:top_n]
    total = sum(count for _, count in top)
    weighted = sum(rating * count for rating, count in top) / total
    return {
        "aggregate_rating": round(weighted, 2),
        "rating_review_count": total,
        "store_count": len(top),
    }


def _search_places(brand: str, api_key: str, region: str, language: str) -> dict:
    """调 Places Text Search。失败返 {"error": ...} 而非 raise。"""
    params = {"query": brand, "key": api_key, "language": language}
    if region:
        params["region"] = region
    try:
        resp = httpx.get(_TEXTSEARCH_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return {"error": f"Places 请求失败（{type(e).__name__}: {e}）"}
    body = resp.json()
    status = body.get("status")
    if status == "OK":
        return {"results": body.get("results", [])}
    if status == "ZERO_RESULTS":
        return {"results": []}
    return {"error": f"Places API status={status}: {body.get('error_message', '')}".strip()}


@tool
def scrape_local_life(brand: str, region: str = "", language: str = "zh-CN") -> str:
    """从 Google Maps 取本地生活品牌的聚合口碑评分（大众点评/美团 类对象用此）。

    返回 JSON，含 aggregate_rating（1–5）/ rating_review_count / store_count / source_url。
    只回评分与评论数，不回评论正文——评论文本请另用 web_search 采集喂 BERT。
    region 可填 ISO 国家码（如 "us"/"sg"）做地域偏置，留空为全球搜索。
    取不到（无 key / 该品牌 Google 上无门店数据 / API 错误）会返 {"found": false, ...}，
    调用方应降级 web_search，多次尝试仍无则按缺失诚信标注。
    """
    cached = react_cache.get("places", {"brand": brand, "region": region})
    if cached is not None:
        return json.dumps(cached, ensure_ascii=False)

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return json.dumps(
            {"brand": brand, "found": False,
             "note": "GOOGLE_MAPS_API_KEY 未配置，请改用 web_search 采集口碑"},
            ensure_ascii=False,
        )

    search = _search_places(brand, api_key, region, language)
    if "error" in search:
        return json.dumps({"brand": brand, "found": False, "note": search["error"]},
                          ensure_ascii=False)

    agg = _aggregate_rating(search["results"])
    if agg is None:
        return json.dumps(
            {"brand": brand, "found": False,
             "note": "Google Maps 上该品牌无可用评分门店（大陆门店常稀疏）"},
            ensure_ascii=False,
        )

    payload = {
        "brand": brand,
        "found": True,
        "rating_source": "google_maps",
        "source_url": f"https://www.google.com/maps/search/{quote(brand)}",
        **agg,
    }
    react_cache.put("places", {"brand": brand, "region": region}, payload)
    return json.dumps(payload, ensure_ascii=False)
