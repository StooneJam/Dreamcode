"""LLM 工具入参 JSON parse + validate 的容错回归。

关键不变量：
- 合法 JSON happy path
- "Extra data"（尾部杂质）应被 raw_decode 救回，不暴露错误给 LLM
- 真坏 JSON 仍返 LLM-friendly 错（含位置 + 上下文）
- Pydantic 校验失败按字段路径列出
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
    """LLM 在合法 JSON 后追加多余 `}` —— 应该被 raw_decode 救，不报错。
    这是 finalize_profile 死循环的根因，回归保护。"""
    obj, err = safe_load_validate('{"name": "x", "score": 1}}', _Sample)
    assert err is None
    assert obj.name == "x"


def test_extra_data_trailing_text_is_recovered() -> None:
    """LLM 在合法 JSON 后追加解释文本（如 markdown / 注释） —— 应被救回。"""
    obj, err = safe_load_validate(
        '{"name": "x", "score": 1}\n以上是我的答案。',
        _Sample,
    )
    assert err is None
    assert obj.name == "x"


def test_malformed_json_returns_friendly_error_with_context() -> None:
    """非 Extra data 类的 JSON 错应返带位置上下文的 LLM-friendly 错误。"""
    obj, err = safe_load_validate('{"name": "x", "score": }', _Sample)
    assert obj is None
    assert err is not None
    assert "char" in err  # 含位置
    assert "出错位置附近的内容" in err  # 含上下文
    assert "只输出一个完整的 JSON 对象" in err  # 含 actionable hint


def test_truncated_json_unclosed_at_end_is_recovered() -> None:
    """Doubao 撞 token 上限把 JSON 截在末尾（括号未闭合）→ 倒退补全救回，不报错。
    与上面 malformed 用例成对：截断（末端未闭合）救，畸形（结构完整值缺失）响亮报错。"""
    obj, err = safe_load_validate('{"name": "x", "score": 1', _Sample)
    assert err is None
    assert obj.name == "x"
    assert obj.score == 1


def test_pydantic_validation_error_lists_field_paths() -> None:
    """Pydantic 失败按 'field.path: msg' 格式列出，LLM 能定位字段。"""
    obj, err = safe_load_validate('{"name": "x", "score": -1}', _Sample)
    assert obj is None
    assert err is not None
    assert "_Sample 校验失败" in err
    assert "score" in err


def test_safe_load_list_recovers_extra_data() -> None:
    """list 入参同样支持 Extra data 救援。"""
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
# repair_llm_json：豆包高频结构错填的容忍式修复
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
    """pre_clean=repair_llm_json：evidence 裸 URL 串第一次就过校验。"""
    from cca.schema import Fact
    items, err = safe_load_list(
        '[{"statement": "s", "evidence": ["https://x.com/a"]}]',
        Fact, pre_clean=repair_llm_json,
    )
    assert err is None
    assert items[0].evidence[0].source_url == "https://x.com/a"
