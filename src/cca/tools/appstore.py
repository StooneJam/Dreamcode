"""App Store 爬取工具 —— 通过 Node.js 子进程调用 app-store-scraper。

依赖：scripts/node/ 下需先执行 `npm install`。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.tools import tool

_NODE_SCRIPT = Path(__file__).parents[3] / "scripts" / "node" / "app_store_scraper.js"


def _run_scraper(product_name: str, country: str, max_reviews: int) -> dict:
    """调用 Node.js 脚本，返回解析后的 JSON dict。"""
    result = subprocess.run(
        ["node", str(_NODE_SCRIPT), product_name, country, str(max_reviews)],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"app-store-scraper 进程异常：{result.stderr[:300]}")
    return json.loads(result.stdout)


@tool
def scrape_app_store(product_name: str, country: str = "cn", max_reviews: int = 50) -> str:
    """从 App Store 爬取应用评分与评论。

    返回 JSON 字符串，包含 rating、review_count 和 reviews 列表。
    每条 review 含 rating（1-5）、title 和 text 字段。
    country 默认 "cn"（中国区），max_reviews 最多 200。
    """
    data = _run_scraper(product_name, country, min(max_reviews, 200))
    return json.dumps(data, ensure_ascii=False)
