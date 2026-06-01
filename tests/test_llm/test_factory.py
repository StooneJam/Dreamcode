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


# ── per-run 凭证注入 ────────────────────────────────────────────────────


def test_no_creds_falls_back_to_env_singletons() -> None:
    assert factory.get_llm("gpt-5") is factory.gpt
    assert factory.get_report_llm() is factory.report_llm
    assert factory.cross_family_enabled() is True


def test_single_key_disables_cross_family_and_collapses_families() -> None:
    creds = {"gpt-5": factory.LLMCredential(api_key="k1", model="qwen-max")}
    with factory.use_credentials(creds):
        assert factory.cross_family_enabled() is False
        # 三个角色槽全塌到唯一 endpoint
        assert factory.get_llm("deepseek").model_name == "qwen-max"
        assert factory.get_llm("doubao").model_name == "qwen-max"


def test_two_keys_enable_cross_family_and_fallback_fills_empty_slot() -> None:
    creds = {
        "gpt-5": factory.LLMCredential(api_key="k1", model="qwen-max"),
        "deepseek": factory.LLMCredential(api_key="k2", model="glm-4"),
    }
    with factory.use_credentials(creds):
        assert factory.cross_family_enabled() is True
        assert factory.get_llm("gpt-5").model_name == "qwen-max"
        assert factory.get_llm("deepseek").model_name == "glm-4"
        # 空 doubao 槽按 _FALLBACK_ORDER 借 gpt-5
        assert factory.get_llm("doubao").model_name == "qwen-max"


def test_two_identical_endpoints_count_as_one() -> None:
    cred = factory.LLMCredential(api_key="k1", model="qwen-max")
    creds = {"gpt-5": cred, "deepseek": cred}
    with factory.use_credentials(creds):
        assert factory.cross_family_enabled() is False


def test_use_credentials_resets_after_exit() -> None:
    creds = {"gpt-5": factory.LLMCredential(api_key="k1", model="qwen-max")}
    with factory.use_credentials(creds):
        pass
    assert factory.get_llm("gpt-5") is factory.gpt
