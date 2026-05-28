"""LLM 工具入参的 JSON parse + Pydantic validate；失败返回 LLM-friendly 错误字符串。

在 create_react_agent 里 raise 异常会中断 ReAct loop，工具应 return 错误信息
作为 ToolMessage，让 LLM 看到后自修参数重试。
"""
from __future__ import annotations

import json
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def _format_decode_error(json_str: str, e: json.JSONDecodeError) -> str:
    """JSONDecodeError → 含位置上下文的 LLM 可自修错误信息。"""
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


def _try_parse_lenient(json_str: str) -> tuple[dict | list | None, str | None]:
    """两阶段 JSON parse：
    1. 严格 json.loads
    2. 失败且原因是 'Extra data' → 用 JSONDecoder().raw_decode 救一下，
       只取第一个完整 JSON 对象，丢弃尾部杂质（LLM 偶尔在 JSON 后追加解释 / 多余 `}`）

    返回 (parsed_obj, None) 或 (None, llm_friendly_error)。
    """
    try:
        return json.loads(json_str), None
    except json.JSONDecodeError as e:
        if e.msg != "Extra data":
            return None, _format_decode_error(json_str, e)

    # 尾部杂质 → 救
    try:
        obj, _end = json.JSONDecoder().raw_decode(json_str.lstrip())
        return obj, None
    except json.JSONDecodeError as e:
        return None, _format_decode_error(json_str, e)


def safe_load_validate(
    json_str: str,
    schema: type[T],
    *,
    pre_clean: Callable[[dict], dict] | None = None,
    hint: str = "",
    max_errors_shown: int = 20,
) -> tuple[T | None, str | None]:
    """parse JSON → 可选清洗 → Pydantic validate。

    返回 (obj, None) 或 (None, llm_friendly_error_str)。
    Extra data 类错误会先尝试 raw_decode 救（丢弃尾部杂质），失败再返错。
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


def safe_load_list(json_str: str, item_schema: type[T]) -> tuple[list[T] | None, str | None]:
    """parse JSON 数组 → 每项 Pydantic validate；任一失败返回错误字符串。"""
    raw, err = _try_parse_lenient(json_str)
    if err:
        return None, err
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
