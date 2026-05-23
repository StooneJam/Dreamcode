"""测试 LLM factory 的派发逻辑（不调真 API）。"""
from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from cca.llm import factory


def test_module_constants_are_chat_openai() -> None:
    assert isinstance(factory.gpt, ChatOpenAI)
    assert isinstance(factory.deepseek, ChatOpenAI)
    assert isinstance(factory.doubao, ChatOpenAI)


def test_get_llm_dispatches_to_correct_family() -> None:
    assert factory.get_llm("gpt-5") is factory.gpt
    assert factory.get_llm("deepseek") is factory.deepseek
    assert factory.get_llm("doubao") is factory.doubao


def test_get_llm_rejects_unknown_family() -> None:
    with pytest.raises(ValueError):
        factory.get_llm("claude")  # type: ignore[arg-type]


def test_deepseek_uses_custom_base_url() -> None:
    assert "deepseek" in str(factory.deepseek.root_client.base_url)


def test_doubao_uses_ark_base_url() -> None:
    assert "volces" in str(factory.doubao.root_client.base_url)
