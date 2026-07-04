"""App Store scraping -- calls app-store-scraper via a Node.js subprocess.

Dependency: run `npm install` in scripts/node/ first; if missing, the tool returns a
JSON error and the LLM naturally falls back to web_search.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.tools import tool

_NODE_SCRIPT = Path(__file__).parents[3] / "scripts" / "node" / "app_store_scraper.js"


def _run_scraper(product_name: str, country: str, max_reviews: int) -> dict:
    """Call the Node script. Returns {"error": ..., "product_name": ...} on failure instead of raising."""
    try:
        result = subprocess.run(
            ["node", str(_NODE_SCRIPT), product_name, country, str(max_reviews)],
            capture_output=True, encoding="utf-8", timeout=60,
        )
    except FileNotFoundError:
        return {"error": "Node.js 未安装或不在 PATH 中。请改用 web_search 抓取评论。",
                "product_name": product_name}
    except subprocess.TimeoutExpired:
        return {"error": "app-store-scraper 子进程超时（60s）。请改用 web_search。",
                "product_name": product_name}

    if result.returncode != 0 and not result.stdout.strip():
        return {"error": f"app-store-scraper 进程异常：{result.stderr[:300]}。"
                          f"可能 npm install 未执行；请改用 web_search 抓取评论。",
                "product_name": product_name}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"app-store-scraper 输出非 JSON：{e}。请改用 web_search。",
                "product_name": product_name}


@tool
def scrape_app_store(product_name: str, country: str = "cn", max_reviews: int = 50) -> str:
    """Scrape an app's rating and reviews from the App Store.

    Returns a JSON string with rating / review_count / a reviews list (each review
    has rating 1-5 / title / text). country defaults to "cn", max_reviews caps at 200.
    On failure (Node missing / timeout / app not found) returns {"error": ...}; the
    caller should fall back to web_search itself.
    """
    data = _run_scraper(product_name, country, min(max_reviews, 200))
    return json.dumps(data, ensure_ascii=False)
