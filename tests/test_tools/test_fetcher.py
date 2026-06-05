"""测试 fetch_url 工具 —— monkeypatch httpx + trafilatura + robotparser，不调真网络。

覆盖 5 个分支：robots 禁止 / HTTP 错误 / 抽取失败 / 成功 / 非法 URL。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from cca.tools import fetcher
from cca.tools.fetcher import fetch_url


@pytest.fixture(autouse=True)
def _clear_robots_cache() -> None:
    """每个测试前清 lru_cache，避免跨测试污染。"""
    fetcher._load_robots.cache_clear()


def _patch_robots_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """robotparser 永远返回 allowed。"""
    mock_rp = MagicMock()
    mock_rp.can_fetch.return_value = True
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: mock_rp)


def _patch_robots_deny_all(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rp = MagicMock()
    mock_rp.can_fetch.return_value = False
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: mock_rp)


def test_fetch_url_robots_denied_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_robots_deny_all(monkeypatch)

    result = fetch_url.invoke({"url": "https://example.com/restricted", "extract_for": "定价"})

    assert "error" in result
    assert "robots.txt" in result["error"]
    assert result["url"] == "https://example.com/restricted"
    assert "fetched_at" in result


def test_fetch_url_invalid_url_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺少 scheme/netloc 的 URL 直接拒掉，不走 HTTP。"""
    result = fetch_url.invoke({"url": "not-a-url", "extract_for": "定价"})

    assert "error" in result
    assert "非法 URL" in result["error"]


def test_fetch_url_http_error_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_robots_allow_all(monkeypatch)
    monkeypatch.setattr(
        fetcher.httpx,
        "get",
        MagicMock(side_effect=httpx.TimeoutException("timeout")),
    )

    result = fetch_url.invoke({"url": "https://slow.example.com/", "extract_for": "定价"})

    assert "error" in result
    assert "TimeoutException" in result["error"]


def test_fetch_url_extract_returns_none_means_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """trafilatura 抽不出正文（SPA / 纯图片）→ 返回 error。"""
    _patch_robots_allow_all(monkeypatch)
    mock_response = MagicMock()
    mock_response.text = "<html><body><script>app()</script></body></html>"
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(fetcher.httpx, "get", MagicMock(return_value=mock_response))
    monkeypatch.setattr(fetcher.trafilatura, "extract", lambda *a, **kw: None)

    result = fetch_url.invoke({"url": "https://spa.example.com/", "extract_for": "定价"})

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
    # 蒸馏 mock：不打真 LLM，并校验抽取正文 + extract_for 透传
    captured = {}

    def fake_distill(text: str, focus: str) -> list[str]:
        captured["text"] = text
        captured["focus"] = focus
        return ["Pro 30元/月"]

    monkeypatch.setattr(fetcher, "distill", fake_distill)

    result = fetch_url.invoke({"url": "https://feishu.cn/pricing", "extract_for": "定价档位"})

    assert "error" not in result
    assert result["url"] == "https://feishu.cn/pricing"
    assert result["title"] == "飞书定价"
    assert result["snippets"] == ["Pro 30元/月"]
    assert "text" not in result  # 整页正文不再进结果，只留片段
    assert "fetched_at" in result
    assert captured["focus"] == "定价档位"
    assert captured["text"] == "Pro 30元/月"  # _smart_truncate 后的正文喂给 distill


def test_robots_check_allows_when_robots_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """robots.txt 读不到（404 / DNS fail）时保守视为允许，跟随业界惯例。"""
    monkeypatch.setattr(fetcher, "_load_robots", lambda _url: None)

    err = fetcher._robots_check("https://nodejs.example.com/page")
    assert err is None


# ── distill None 降级 ─────────────────────────────────────────────────


def test_distill_returns_verbatim_when_structured_output_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """function_calling 返 None → 原文当单条片段兜底，不崩。"""
    from cca.tools import _distill

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = None
    mock_bound = MagicMock()
    mock_bound.with_structured_output.return_value = mock_llm
    monkeypatch.setattr(_distill, "get_llm", lambda _family: mock_bound)

    result = _distill.distill("飞书 Pro 版 30 元每月", "定价")

    assert result == ["飞书 Pro 版 30 元每月"]
