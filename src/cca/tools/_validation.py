"""LLM 工具入参的 JSON parse + Pydantic validate；失败返回 LLM-friendly 错误字符串。

在 create_react_agent 里 raise 异常会中断 ReAct loop，工具应 return 错误信息
作为 ToolMessage，让 LLM 看到后自修参数重试。
"""
from __future__ import annotations

import json
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


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
    """
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, (
            f"参数不是合法 JSON：{e.msg}（line {e.lineno} col {e.colno}）。"
            f"请检查引号、逗号、转义符（中文文本中的双引号需 \\\" 转义），重新生成完整 JSON 后重试。"
        )

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
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, (
            f"参数不是合法 JSON：{e.msg}（line {e.lineno} col {e.colno}）。"
            f"请检查引号、逗号、转义符，重新生成完整 JSON 数组后重试。"
        )
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
