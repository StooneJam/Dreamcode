"""JSON parse + Pydantic validate for LLM tool arguments; returns an LLM-friendly error string on failure.

Raising inside create_react_agent aborts the ReAct loop, so a tool should return the
error as a ToolMessage instead, letting the LLM see it and retry with corrected arguments.
"""
from __future__ import annotations

import json
import re
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# structural repairs for mistakes the LLM (especially Doubao) repeatedly makes,
# keyed by field name convention; never adds or alters semantic data.
_EVIDENCE_URL_ALIASES = ("source_url", "url", "link", "href", "uri")
_EVIDENCE_KEYS = ("evidence", "sources")
_THEME_LIST_KEYS = ("positive_themes", "negative_themes", "included_features")
_SPLIT_RE = re.compile(r"[,，、;；\n]+")


def _coerce_evidence(item: object) -> object:
    """Normalize anything that belongs in an Evidence slot into an object with source_url.

    A URL string / {url|link|href:...} -> {source_url:...}; an object that already
    has source_url passes through unchanged. This is Doubao's most frequent mistake
    (filling Evidence with a bare URL); normalizing it here passes validation on the
    first try and avoids a retry.
    """
    if isinstance(item, str):
        return {"source_url": item}
    if isinstance(item, dict) and not item.get("source_url"):
        for alias in _EVIDENCE_URL_ALIASES:
            val = item.get(alias)
            if isinstance(val, str) and val:
                return {**item, "source_url": val}
    return item


def repair_llm_json(raw: object) -> object:
    """Recursively repair common LLM structural mistakes (by field name), so Pydantic
    passes on the first try and ReAct retries are reduced:

    - evidence / sources: an Evidence list -- elements that are bare URL strings or
      {url:...} become {source_url:...}; a single object (not a list) gets wrapped in one
    - source: a single Evidence -- normalized the same way
    - positive_themes / negative_themes / included_features: a single string gets split into a list by delimiter
    """
    if isinstance(raw, list):
        return [repair_llm_json(x) for x in raw]
    if not isinstance(raw, dict):
        return raw
    out: dict = {}
    for key, val in raw.items():
        if key in _EVIDENCE_KEYS:
            items = val if isinstance(val, list) else [val]
            out[key] = [_coerce_evidence(repair_llm_json(it)) for it in items]
        elif key == "source":
            out[key] = _coerce_evidence(val) if val is not None else None
        elif key in _THEME_LIST_KEYS and isinstance(val, str):
            out[key] = [t.strip() for t in _SPLIT_RE.split(val) if t.strip()]
        else:
            out[key] = repair_llm_json(val)
    return out


def _format_decode_error(json_str: str, e: json.JSONDecodeError) -> str:
    """JSONDecodeError -> an LLM-fixable error message that includes positional context."""
    pos = e.pos
    ctx_start = max(0, pos - 40)
    ctx_end = min(len(json_str), pos + 40)
    snippet = json_str[ctx_start:ctx_end].replace("\n", "\\n")
    head = f"...{snippet}..." if ctx_start > 0 or ctx_end < len(json_str) else snippet
    return (
        f"参数不是合法 JSON：{e.msg}（char {pos}, line {e.lineno} col {e.colno}）。\n"
        f"出错位置附近的内容（±40 char）：\n  {head}\n"
        f"请检查引号、逗号、转义符（中文双引号需 \\\" 转义），"
        f"**只输出一个完整的 JSON 对象**，不要附加任何解释文本或多余的尾部内容。"
    )



def _scan_structure(s: str) -> tuple[list[str], bool]:
    """Scan a JSON string, returning (brackets that need closing, whether it ends inside a string)."""
    stack: list[str] = []
    in_str = False
    esc = False
    for c in s:
        if esc:
            esc = False
            continue
        if c == "\\" and in_str:
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c in ("{", "["):
            stack.append("}" if c == "{" else "]")
        elif c in ("}", "]") and stack:
            stack.pop()
    return list(reversed(stack)), in_str


def _try_recover_truncated(json_str: str) -> tuple[dict | list | None, None]:
    """Truncation recovery: back off character by character from the end until a
    valid boundary is found, then close quotes+brackets.

    Doubao's token limit can truncate JSON either inside a string (needs a closing
    `"`) or inside brackets (needs `}` / `]`). Backs off at most 1200 characters;
    returns (None, None) if unrecoverable.
    """
    s = json_str.rstrip()
    for trim in range(0, min(1200, len(s))):
        candidate = s[: len(s) - trim] if trim else s
        closing_brackets, ends_in_str = _scan_structure(candidate)
        closing = "".join(closing_brackets)
        # try both: close brackets directly / close the string first then brackets
        variants = [candidate + closing]
        if ends_in_str:
            variants.append(candidate + '"' + closing)
        for completed in variants:
            try:
                return json.loads(completed), None
            except json.JSONDecodeError:
                pass
    return None, None


def _try_parse_lenient(json_str: str) -> tuple[dict | list | None, str | None]:
    """Three-stage JSON parse:
    1. strict json.loads
    2. 'Extra data' -> raw_decode grabs the first complete object, discarding trailing junk
    3. other errors (including mid-truncation) -> back off and close brackets, retry; only errors if that also fails

    Returns (parsed_obj, None) or (None, llm_friendly_error).
    """
    try:
        return json.loads(json_str), None
    except json.JSONDecodeError:
        pass

    # trailing junk -> rescue
    try:
        obj, _end = json.JSONDecoder().raw_decode(json_str.lstrip())
        return obj, None
    except json.JSONDecodeError:
        pass

    # mid-truncation (Doubao's token limit) -> back off and close. Only attempted
    # when the tail is genuinely unclosed (unpaired brackets or ends inside a
    # string) -- otherwise malformed-but-structurally-complete JSON like
    # {"score": } (a real error the model could fix itself) would get silently
    # rescued down to {} by backing off too far.
    pending, ends_in_str = _scan_structure(json_str)
    if pending or ends_in_str:
        recovered, _ = _try_recover_truncated(json_str)
        if recovered is not None:
            return recovered, None

    # every rescue failed, return the original error for the LLM to fix
    try:
        json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, _format_decode_error(json_str, e)
    return None, "JSON 解析失败（未知原因）"


def safe_load_validate(
    json_str: str,
    schema: type[T],
    *,
    pre_clean: Callable[[dict], dict] | None = None,
    hint: str = "",
    max_errors_shown: int = 20,
) -> tuple[T | None, str | None]:
    """parse JSON -> optional cleanup -> Pydantic validate.

    Returns (obj, None) or (None, llm_friendly_error_str).
    'Extra data' errors are first rescued via raw_decode (discarding trailing junk); errors otherwise.
    """
    raw, err = _try_parse_lenient(json_str)
    if err:
        return None, err

    if pre_clean is not None:
        raw = pre_clean(raw)

    try:
        return schema.model_validate(raw), None
    except ValidationError as e:
        errs = [f"  · {'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        msg = f"{schema.__name__} 校验失败，请按以下错误修正后重试：\n" + "\n".join(errs[:max_errors_shown])
        if len(errs) > max_errors_shown:
            msg += f"\n  …还有 {len(errs) - max_errors_shown} 条错误未列出"
        if hint:
            msg += f"\n\n{hint}"
        return None, msg


def safe_load_list(
    json_str: str,
    item_schema: type[T],
    *,
    pre_clean: Callable[[object], object] | None = None,
) -> tuple[list[T] | None, str | None]:
    """parse a JSON array -> optional cleanup -> Pydantic validate each item; any failure returns an error string."""
    raw, err = _try_parse_lenient(json_str)
    if err:
        return None, err
    if pre_clean is not None:
        raw = pre_clean(raw)
    if not isinstance(raw, list):
        return None, f"参数必须是 JSON 数组，实际为 {type(raw).__name__}。"

    items: list[T] = []
    for i, entry in enumerate(raw):
        try:
            items.append(item_schema.model_validate(entry))
        except ValidationError as e:
            errs = [f"  · {'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            return None, (
                f"数组第 {i} 项 {item_schema.__name__} 校验失败：\n" +
                "\n".join(errs[:10])
            )
    return items, None
