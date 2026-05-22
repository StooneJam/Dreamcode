"""测试 web_search 包装 —— monkeypatch Tavily，不调真 API。"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from cca.tools import search


def test_web_search_returns_results_list(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "飞书官网", "url": "https://feishu.cn", "content": "..."},
        ]
    }
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = search.web_search("飞书 主要竞品", max_results=3)

    assert len(results) == 1
    assert results[0]["url"] == "https://feishu.cn"
    mock_client.search.assert_called_once_with("飞书 主要竞品", max_results=3)


def test_web_search_returns_empty_on_missing_results_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {}
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = search.web_search("无结果查询")

    assert results == []


def test_web_search_uses_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_client(api_key: str) -> MagicMock:
        captured["api_key"] = api_key
        m = MagicMock()
        m.search.return_value = {"results": []}
        return m

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(search, "TavilyClient", fake_client)

    search.web_search("anything")

    assert captured["api_key"] == "tvly-test-key"
