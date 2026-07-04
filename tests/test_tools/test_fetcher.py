"""Tests for the fetch_url tool -- monkeypatches httpx + trafilatura + robotparser, no real network calls.

Covers 5 branches: robots disallow / HTTP error / extraction failure / success / invalid URL.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from cca.tools import fetcher
from cca.tools.fetcher import fetch_url


@pytest.fixture(autouse=True)
def _clear_robots_cache() -> None:
    """Clear the lru_cache before every test, to avoid cross-test contamination."""
    fetcher._load_robots.cache_clear()


def _patch_robots_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """robotparser always returns allowed."""
    mock_rp = MagicMock()
    mock_rp.can_fetch.return_value = True
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: mock_rp)


def _patch_robots_deny_all(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rp = MagicMock()
    mock_rp.can_fetch.return_value = False
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: mock_rp)


def test_fetch_url_robots_denied_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_robots_deny_all(monkeypatch)

    result = fetch_url.invoke({"url": "https://example.com/restricted"})

    assert "error" in result
    assert "robots.txt" in result["error"]
    assert result["url"] == "https://example.com/restricted"
    assert "fetched_at" in result


def test_fetch_url_invalid_url_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A URL missing scheme/netloc is rejected directly, never reaching HTTP."""
    result = fetch_url.invoke({"url": "not-a-url"})

    assert "error" in result
    assert "非法 URL" in result["error"]


def test_fetch_url_http_error_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_robots_allow_all(monkeypatch)
    monkeypatch.setattr(
        fetcher.httpx,
        "get",
        MagicMock(side_effect=httpx.TimeoutException("timeout")),
    )

    result = fetch_url.invoke({"url": "https://slow.example.com/"})

    assert "error" in result
    assert "TimeoutException" in result["error"]


def test_fetch_url_extract_returns_none_means_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """trafilatura can't extract a body (SPA/image-only page) -> returns an error."""
    _patch_robots_allow_all(monkeypatch)
    mock_response = MagicMock()
    mock_response.text = "<html><body><script>app()</script></body></html>"
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(fetcher.httpx, "get", MagicMock(return_value=mock_response))
    monkeypatch.setattr(fetcher.trafilatura, "extract", lambda *a, **kw: None)

    result = fetch_url.invoke({"url": "https://spa.example.com/"})

    assert "error" in result
    assert "提取正文" in result["error"]


def test_fetch_url_success_returns_snippets_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_robots_allow_all(monkeypatch)
    mock_response = MagicMock()
    mock_response.text = "<html><head><title>飞书定价</title></head><body><p>Pro 30元/月</p></body></html>"
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(fetcher.httpx, "get", MagicMock(return_value=mock_response))
    monkeypatch.setattr(
        fetcher.trafilatura, "extract", lambda *a, **kw: "Pro 30元/月"
    )
    mock_meta = MagicMock()
    mock_meta.title = "飞书定价"
    monkeypatch.setattr(
        fetcher.trafilatura, "extract_metadata", lambda _html: mock_meta
    )

    result = fetch_url.invoke({"url": "https://feishu.cn/pricing"})

    assert "error" not in result
    assert result["url"] == "https://feishu.cn/pricing"
    assert result["title"] == "飞书定价"
    # the full page body (after _smart_truncate) goes into snippets as a single entry, unmodified
    assert result["snippets"] == ["Pro 30元/月"]
    assert "text" not in result  # only the snippets field is kept, text is never exposed
    assert "fetched_at" in result


def test_robots_check_allows_when_robots_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When robots.txt is unreadable (404/DNS failure), conservatively treat it as allowed, following industry convention."""
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: None)

    err = fetcher._robots_check("https://nodejs.example.com/page")
    assert err is None
