"""
测试 web_search @tool 包装 —— monkeypatch Tavily，不调真 API。
 web_search 是 BaseTool 对象.
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
    mock_client.search.assert_called_once_with("飞书 主要竞品", max_results=3)


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


def test_web_search_returns_error_string_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-035：限流（运营类）必须返错误串而非 raise，否则一次外部失败打死整张图。"""
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
    """瞬时网络失败（ConnectionError）同样降级为错误串。"""
    mock_client = MagicMock()
    mock_client.search.side_effect = requests.ConnectionError("connection reset")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    result = web_search.invoke({"query": "x"})

    assert isinstance(result, str)
    assert "web_search 暂不可用" in result


def test_web_search_propagates_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置/认证类（InvalidAPIKeyError）故意不吞，响亮 raise（CLAUDE.md §1 失败要响亮）。"""
    from tavily.errors import InvalidAPIKeyError

    mock_client = MagicMock()
    mock_client.search.side_effect = InvalidAPIKeyError("401 unauthorized")
    monkeypatch.setattr(search, "TavilyClient", lambda api_key: mock_client)

    with pytest.raises(InvalidAPIKeyError):
        web_search.invoke({"query": "x"})


def test_web_search_is_a_langchain_tool() -> None:
    """验证 @tool 装饰生效，可被 LLM bind_tools 使用。"""
    from langchain_core.tools import BaseTool

    assert isinstance(web_search, BaseTool)
    assert web_search.name == "web_search"
    # docstring 第一段应能作为 description 给 LLM 看
    assert "Search the public web" in (web_search.description or "")
