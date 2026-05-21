"""共享 pytest fixtures —— agent / skill / tool 三层测试共用。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_sources():
    """模拟采集到的源数据（飞书/钉钉等），用于测试下游 agent 的输入。"""
    with open(FIXTURES_DIR / "mock_sources.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_llm_responses():
    """按 key 索引的假 LLM 返回，用于离线测试避免烧 API 配额。"""
    with open(FIXTURES_DIR / "mock_llm_responses.json", encoding="utf-8") as f:
        return json.load(f)


class FakeLLM:
    """最简假 LLM 客户端 —— 单元测试默认注入此对象，绝不调真 API。"""

    def __init__(self, responses: dict):
        self.responses = responses
        self.call_log: list[dict] = []

    def invoke(self, key: str, prompt: str | None = None):
        self.call_log.append({"key": key, "prompt_preview": (prompt or "")[:200]})
        return self.responses.get(key, f"<no mock for {key!r}>")


@pytest.fixture
def fake_llm(mock_llm_responses):
    return FakeLLM(mock_llm_responses)
