"""Regression tests for LLM tool argument JSON parse + validate's error tolerance.

Key invariants:
- valid JSON happy path
- "Extra data" (trailing junk) should be rescued by raw_decode, without exposing an error to the LLM
- genuinely broken JSON still returns an LLM-friendly error (with position + context)
- Pydantic validation failures are listed by field path
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from cca.tools._validation import repair_llm_json, safe_load_list, safe_load_validate


class _Sample(BaseModel):
    name: str
    score: int = Field(ge=0)


def test_happy_path() -> None:
    obj, err = safe_load_validate('{"name": "x", "score": 1}', _Sample)
    assert err is None
    assert obj.name == "x"
    assert obj.score == 1


def test_extra_data_trailing_brace_is_recovered() -> None:
    """The LLM appends an extra `}` after valid JSON -- should be rescued by
    raw_decode without erroring. This was the root cause of finalize_profile's
    infinite loop; regression guard."""
    obj, err = safe_load_validate('{"name": "x", "score": 1}}', _Sample)
    assert err is None
    assert obj.name == "x"


def test_extra_data_trailing_text_is_recovered() -> None:
    """The LLM appends explanatory text after valid JSON (e.g. markdown/comments) -- should be rescued."""
    obj, err = safe_load_validate(
        '{"name": "x", "score": 1}\n以上是我的答案。',
        _Sample,
    )
    assert err is None
    assert obj.name == "x"


def test_malformed_json_returns_friendly_error_with_context() -> None:
    """A non-Extra-data JSON error should return an LLM-friendly error with positional context."""
    obj, err = safe_load_validate('{"name": "x", "score": }', _Sample)
    assert obj is None
    assert err is not None
    assert "char" in err  # includes position
    assert "出错位置附近的内容" in err  # includes context
    assert "只输出一个完整的 JSON 对象" in err  # includes an actionable hint


def test_truncated_json_unclosed_at_end_is_recovered() -> None:
    """Doubao hits its token limit and truncates JSON at the end (unclosed brackets)
    -> backing off and closing rescues it, no error. Pairs with the malformed test
    case above: truncation (unclosed at the end) is rescued, malformed (structurally
    complete but a missing value) errors loudly."""
    obj, err = safe_load_validate('{"name": "x", "score": 1', _Sample)
    assert err is None
    assert obj.name == "x"
    assert obj.score == 1


def test_pydantic_validation_error_lists_field_paths() -> None:
    """A Pydantic failure is listed as 'field.path: msg', so the LLM can locate the field."""
    obj, err = safe_load_validate('{"name": "x", "score": -1}', _Sample)
    assert obj is None
    assert err is not None
    assert "_Sample 校验失败" in err
    assert "score" in err


def test_safe_load_list_recovers_extra_data() -> None:
    """A list argument likewise supports Extra data rescue."""
    items, err = safe_load_list('[{"name": "a", "score": 1}]]', _Sample)
    assert err is None
    assert len(items) == 1
    assert items[0].name == "a"


def test_safe_load_list_rejects_non_list() -> None:
    items, err = safe_load_list('{"name": "a", "score": 1}', _Sample)
    assert items is None
    assert "必须是 JSON 数组" in err


def test_hint_appended_on_validation_failure() -> None:
    obj, err = safe_load_validate(
        '{"name": "x", "score": -1}', _Sample,
        hint="字段规则提示：score 必须 >= 0",
    )
    assert obj is None
    assert "字段规则提示" in err


# ---------------------------------------------------------------------------
# repair_llm_json: tolerant repair of Doubao's frequent structural mistakes
# ---------------------------------------------------------------------------

class TestRepairLLMJson:
    def test_bare_url_string_in_evidence_becomes_object(self) -> None:
        fixed = repair_llm_json({"evidence": ["https://x.com/a"]})
        assert fixed["evidence"] == [{"source_url": "https://x.com/a"}]

    def test_url_key_in_evidence_mapped_to_source_url(self) -> None:
        fixed = repair_llm_json({"evidence": [{"url": "https://x.com", "snippet": "s"}]})
        assert fixed["evidence"][0]["source_url"] == "https://x.com"
        assert fixed["evidence"][0]["snippet"] == "s"

    def test_single_evidence_object_wrapped_into_list(self) -> None:
        fixed = repair_llm_json({"evidence": {"source_url": "https://x.com"}})
        assert fixed["evidence"] == [{"source_url": "https://x.com"}]

    def test_source_url_string_becomes_object(self) -> None:
        fixed = repair_llm_json({"source": "https://x.com"})
        assert fixed["source"] == {"source_url": "https://x.com"}

    def test_none_source_stays_none(self) -> None:
        assert repair_llm_json({"source": None})["source"] is None

    def test_themes_string_split_into_list(self) -> None:
        fixed = repair_llm_json({"positive_themes": "性价比高、出餐快,雪王亲民"})
        assert fixed["positive_themes"] == ["性价比高", "出餐快", "雪王亲民"]

    def test_valid_object_untouched(self) -> None:
        valid = {"evidence": [{"source_url": "https://x.com", "snippet": "s"}]}
        assert repair_llm_json(valid)["evidence"][0]["source_url"] == "https://x.com"

    def test_nested_under_dimensions(self) -> None:
        raw = {"dimensions": [{"facts": [{"statement": "s", "evidence": ["https://x.com"]}]}]}
        fixed = repair_llm_json(raw)
        assert fixed["dimensions"][0]["facts"][0]["evidence"] == [{"source_url": "https://x.com"}]


def test_safe_load_list_applies_pre_clean() -> None:
    """pre_clean=repair_llm_json: a bare URL string in evidence passes validation on the first try."""
    from cca.schema import Fact
    items, err = safe_load_list(
        '[{"statement": "s", "evidence": ["https://x.com/a"]}]',
        Fact, pre_clean=repair_llm_json,
    )
    assert err is None
    assert items[0].evidence[0].source_url == "https://x.com/a"
