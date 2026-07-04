"""
Tests for the web_search @tool wrapper -- monkeypatches Tavily, no real API calls.
web_search is a BaseTool object.
"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
import requests
from cca.tools import search
from cca.tools.search import web_search


def test_web_search_returns_results_list(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "飞书官网", "url": "https://feishu.cn", "content": "..."},
        ]
    }
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = web_search.invoke({"query": "飞书 主要竞品", "max_results": 3})

    assert len(results) == 1
    assert results[0]["url"] == "https://feishu.cn"
    mock_client.search.assert_called_once_with("飞书 主要竞品", max_results=3, timeout=30)


def test_web_search_truncates_long_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """content stays in history throughout; anything over the cap is truncated locally (cost control)."""
    long_content = "价" * 5000
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [{"title": "x", "url": "https://x.com", "content": long_content}]
    }
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = web_search.invoke({"query": "x"})

    assert len(results[0]["content"]) == search._MAX_RESULT_CONTENT


def test_web_search_caps_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the LLM passes an oversized max_results, the server clamps it to _MAX_RESULTS_CAP."""
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    web_search.invoke({"query": "x", "max_results": 50})

    mock_client.search.assert_called_once_with("x", max_results=search._MAX_RESULTS_CAP, timeout=30)


def test_web_search_drops_extraneous_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Noise fields like raw_content/score in Tavily's result don't enter history, only title/url/content are kept."""
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [{
            "title": "t", "url": "https://x.com", "content": "c",
            "raw_content": "整页超长正文" * 1000, "score": 0.9,
        }]
    }
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = web_search.invoke({"query": "x"})

    assert set(results[0].keys()) == {"title", "url", "content"}


def test_web_search_returns_empty_on_missing_results_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {}
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    results = web_search.invoke({"query": "无结果查询"})

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

    web_search.invoke({"query": "anything"})

    assert captured["api_key"] == "tvly-test-key"


def test_web_search_prefers_run_uploaded_key_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user-uploaded per-run key takes priority over the .env project key."""
    captured = {}

    def fake_client(api_key: str) -> MagicMock:
        captured["api_key"] = api_key
        m = MagicMock()
        m.search.return_value = {"results": []}
        return m

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-project-key")
    monkeypatch.setattr(search, "TavilyClient", fake_client)

    with search.use_tavily_key("tvly-user-key"):
        web_search.invoke({"query": "anything"})

    assert captured["api_key"] == "tvly-user-key"


def test_web_search_falls_back_to_env_when_no_run_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When nothing was uploaded (contextvar is None), falls back to the project's own .env key."""
    captured = {}

    def fake_client(api_key: str) -> MagicMock:
        captured["api_key"] = api_key
        m = MagicMock()
        m.search.return_value = {"results": []}
        return m

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-project-key")
    monkeypatch.setattr(search, "TavilyClient", fake_client)

    with search.use_tavily_key(None):
        web_search.invoke({"query": "anything"})

    assert captured["api_key"] == "tvly-project-key"


def test_validate_tavily_key_returns_none_when_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    assert search.validate_tavily_key("tvly-good") is None


def test_validate_tavily_key_returns_error_string_when_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid key returns an error string for the frontend to prompt a re-upload, without raising."""
    from tavily.errors import InvalidAPIKeyError

    mock_client = MagicMock()
    mock_client.search.side_effect = InvalidAPIKeyError("401 unauthorized")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    err = search.validate_tavily_key("tvly-bad")

    assert isinstance(err, str)
    assert "校验失败" in err


def test_web_search_returns_error_string_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-035: a rate limit (operational) must return an error string instead of
    raising, or one external failure would kill the entire graph."""
    from tavily.errors import UsageLimitExceededError

    mock_client = MagicMock()
    mock_client.search.side_effect = UsageLimitExceededError("blocked: excessive requests")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    result = web_search.invoke({"query": "飞书 竞品"})

    assert isinstance(result, str)
    assert "web_search 暂不可用" in result
    assert "excessive requests" in result


def test_web_search_returns_error_string_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient network failure (ConnectionError) likewise degrades to an error string."""
    mock_client = MagicMock()
    mock_client.search.side_effect = requests.ConnectionError("connection reset")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    result = web_search.invoke({"query": "x"})

    assert isinstance(result, str)
    assert "web_search 暂不可用" in result


def test_web_search_propagates_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A config/auth error (InvalidAPIKeyError) is deliberately not swallowed -- it
    raises loudly (CLAUDE.md §1: failures should be loud)."""
    from tavily.errors import InvalidAPIKeyError

    mock_client = MagicMock()
    mock_client.search.side_effect = InvalidAPIKeyError("401 unauthorized")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    with pytest.raises(InvalidAPIKeyError):
        web_search.invoke({"query": "x"})


def test_web_search_is_a_langchain_tool() -> None:
    """Verifies the @tool decorator took effect, so it can be used by the LLM's bind_tools."""
    from langchain_core.tools import BaseTool

    assert isinstance(web_search, BaseTool)
    assert web_search.name == "web_search"
    # the docstring's first paragraph should work as the description shown to the LLM
    assert "Search the public web" in (web_search.description or "")
