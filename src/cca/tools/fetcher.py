"""HTTP fetch + body extraction. Checks robots.txt before fetching (for compliance).

Any error (robots disallow / timeout / HTTP error / extraction failure) returns
{"url", "error", "fetched_at"}; the ReAct agent sees the error and switches URLs
itself -- no retrying inside the tool.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from urllib import robotparser
from urllib.parse import urlparse

import httpx
import trafilatura
from langchain_core.tools import tool

_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (compatible; CCA-Collector/0.1)"
_MAX_TEXT = 12_000


def _score_paragraph(para: str) -> float:
    if len(para) < 10:
        return 0.0
    score = len(re.findall(r"\d", para)) * 0.2
    if re.match(r"^\s*[-•·*]|\d+\.", para):
        score += 1.5
    length = len(para)
    if 30 < length < 300:
        score += 1.0
    elif 300 <= length < 600:
        score += 0.5
    return score


def _smart_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    print(f"  [fetch_url] truncate {len(text)} → {limit} chars (saved {len(text)-limit})", flush=True)
    paragraphs = [p for p in re.split(r"\n+", text) if p.strip()]
    scored = sorted(enumerate(paragraphs), key=lambda x: _score_paragraph(x[1]), reverse=True)
    selected: set[int] = set()
    total = 0
    for idx, para in scored:
        if total + len(para) + 1 > limit:
            continue
        selected.add(idx)
        total += len(para) + 1
    return "\n".join(p for i, p in enumerate(paragraphs) if i in selected)


@lru_cache(maxsize=256)
def _load_robots(robots_url: str) -> robotparser.RobotFileParser | None:
    """Cache the robots.txt parser per domain. Returns None if unreadable (conservatively treated as allowed)."""
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        # not using rp.read(): its internal urllib.urlopen has no timeout, so a slow
        # or hanging robots server blocks forever, freezing the whole ReAct branch
        # (this happened with gucci.com). Fetch with httpx (which has _TIMEOUT) and parse instead.
        resp = httpx.get(
            robots_url, timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT}, follow_redirects=True,
        )
        resp.raise_for_status()
        rp.parse(resp.text.splitlines())
        return rp
    except Exception:
        return None


def _robots_check(url: str) -> str | None:
    """Check robots.txt. Returns None if allowed, an error string if disallowed."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return f"非法 URL: {url}"
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = _load_robots(robots_url)
    if rp is None:
        return None  # robots.txt unreadable, conservatively allowed
    if not rp.can_fetch(_USER_AGENT, url):
        return f"robots.txt 禁止抓取 {url}"
    return None


@tool
def fetch_url(url: str) -> dict:
    """Fetch a URL and return the page text for evidence extraction.

    Use this AFTER web_search when you need the content of a specific page
    (pricing tables, feature lists, official product pages) to copy precise
    verbatim passages for Fact.evidence binding.

    Args:
        url: Full URL to fetch.

    Returns:
        Success: {"url", "title", "snippets": [...], "fetched_at"} — snippets[0]
        is the (truncated) page text; copy verbatim passages from it as
        Evidence.snippet.
        Failure: {"url", "error", "fetched_at"} — switch to a different URL or
        rely on web_search snippets instead.
    """
    now = datetime.now(timezone.utc).isoformat()

    blocked = _robots_check(url)
    if blocked:
        return {"url": url, "error": blocked, "fetched_at": now}

    try:
        response = httpx.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        return {
            "url": url,
            "error": f"HTTP {type(e).__name__}: {e}",
            "fetched_at": now,
        }

    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=True,
    )
    if not extracted:
        return {"url": url, "error": "页面无法提取正文（可能是 SPA 或纯图片页）", "fetched_at": now}

    metadata = trafilatura.extract_metadata(response.text)
    title = metadata.title if metadata else None

    return {
        "url": url,
        "title": title,
        "snippets": [_smart_truncate(extracted, _MAX_TEXT)],
        "fetched_at": now,
    }
