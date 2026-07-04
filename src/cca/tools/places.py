"""Google Places structured sentiment data -- brand-level ratings for local-life
channels (Dianping/Meituan-type venues).

The official Text Search API returns each venue's rating + user_ratings_total
directly, with global coverage -- far better for cross-border competitors than
scraping Amap/Dianping. Brand-level scores are aggregated across venues via a
top-N weighted average.
Only returns rating + review count, never review text -- sentiment-theme review
text still goes through web_search.
Results are cached in store.db (reusing react_cache) to avoid repeat billing; a
missing key fails soft and the LLM naturally falls back.
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
    """Top-N weighted average: weights each venue's rating by its review count. Returns None if no venue is usable."""
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
    """Call Places Text Search. Returns {"error": ...} on failure instead of raising."""
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
    """Get a local-life brand's aggregated sentiment rating from Google Maps (for Dianping/Meituan-type venues).

    Returns JSON with aggregate_rating (1-5) / rating_review_count / store_count / source_url.
    Only returns rating and review count, never review text -- collect review text
    separately via web_search and judge sentiment from it yourself.
    region accepts an ISO country code (e.g. "us"/"sg") to bias the search; leave
    empty for a global search.
    Returns {"found": false, ...} on failure (no key / no venue data for this brand
    on Google / API error); the caller should fall back to web_search, and note the
    gap honestly if repeated attempts still find nothing.
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
