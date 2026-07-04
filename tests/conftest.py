"""Shared pytest fixtures -- used across agent/skill/tool test layers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from fixtures.mock_state import make_mock_state  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_sources():
    """Simulated collected source data (Feishu/DingTalk etc.), used as input for downstream agent tests."""
    with open(FIXTURES_DIR / "mock_sources.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_llm_responses():
    """Fake LLM responses indexed by key, for offline tests that avoid burning API quota."""
    with open(FIXTURES_DIR / "mock_llm_responses.json", encoding="utf-8") as f:
        return json.load(f)


class FakeLLM:
    """The simplest fake LLM client -- unit tests inject this by default, never calling a real API."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.call_log: list[dict] = []

    def invoke(self, key: str, prompt: str | None = None):
        self.call_log.append({"key": key, "prompt_preview": (prompt or "")[:200]})
        return self.responses.get(key, f"<no mock for {key!r}>")


@pytest.fixture
def fake_llm(mock_llm_responses):
    return FakeLLM(mock_llm_responses)


@pytest.fixture
def mock_state():
    """A complete CCAState after phase 2, for Report Agent tests."""
    return make_mock_state(invoke_reviewer=False)


@pytest.fixture
def mock_state_with_reviewer():
    """Same as above, but with the Doubao final-review switch on."""
    return make_mock_state(invoke_reviewer=True)
