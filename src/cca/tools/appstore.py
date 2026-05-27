"""App Store 爬取 —— Node.js 子进程调用 app-store-scraper。

依赖：scripts/node/ 先执行 `npm install`；未装时工具返 JSON 错误，LLM 自然换 web_search。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.tools import tool

_NODE_SCRIPT = Path(__file__).parents[3] / "scripts" / "node" / "app_store_scraper.js"


def _run_scraper(product_name: str, country: str, max_reviews: int) -> dict:
    """调 Node 脚本。失败时返 {"error": ..., "product_name": ...} 而非 raise。"""
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
    """从 App Store 爬取应用评分与评论。

    返回 JSON 字符串，含 rating / review_count / reviews 列表（每条 review 含 rating 1-5 / title / text）。
    country 默认 "cn"（中国区），max_reviews 最多 200。
    失败（Node 未装 / 超时 / 找不到应用）会返 {"error": ...}；调用方应自行降级 web_search。
    """
    data = _run_scraper(product_name, country, min(max_reviews, 200))
    return json.dumps(data, ensure_ascii=False)
