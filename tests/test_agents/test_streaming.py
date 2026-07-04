"""Tests for _sum_usage's cache-hit token accounting (both provider paths)."""
from __future__ import annotations

from langchain_core.messages import AIMessage

from cca.agents._streaming import _sum_usage


def _ai(
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read: int | None = None,
    deepseek_hit: int | None = None,
) -> AIMessage:
    usage_metadata: dict = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if cache_read is not None:
        usage_metadata["input_token_details"] = {"cache_read": cache_read}
    response_metadata: dict = {}
    if deepseek_hit is not None:
        response_metadata["token_usage"] = {"prompt_cache_hit_tokens": deepseek_hit}
    return AIMessage(
        content="", usage_metadata=usage_metadata, response_metadata=response_metadata
    )


def test_sum_usage_reads_openai_cache_read() -> None:
    usage = _sum_usage([_ai(100, 20, cache_read=80)])
    assert usage == {"input": 100, "output": 20, "cached": 80, "total": 120}


def test_sum_usage_falls_back_to_deepseek_cache_hit() -> None:
    """When the OpenAI-style field is missing, falls back to DeepSeek's prompt_cache_hit_tokens."""
    usage = _sum_usage([_ai(100, 20, deepseek_hit=70)])
    assert usage["cached"] == 70
    assert usage["input"] == 100


def test_sum_usage_zero_when_no_cache_field() -> None:
    usage = _sum_usage([_ai(100, 20)])
    assert usage == {"input": 100, "output": 20, "cached": 0, "total": 120}
