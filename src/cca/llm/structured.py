"""LLM structured-output compatibility layer -- for reasoning models that don't
support tool_choice / response_format.

Usage (in place of llm.with_structured_output(MyModel)):
    from cca.llm.structured import invoke_structured
    result = invoke_structured(deepseek, messages, MyModel)

How it works:
    Append the JSON Schema to the last HumanMessage, asking the model for valid JSON;
    extract the JSON block from the reply via regex and parse it with Pydantic.
    Doesn't rely on response_format / tool_choice, so it works with every DeepSeek
    model including reasoning variants.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def invoke_structured(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    output_class: Type[T],
) -> T:
    """Invoke the LLM and parse the response into the given Pydantic model."""
    schema_str = json.dumps(output_class.model_json_schema(), ensure_ascii=False, indent=2)
    instruction = (
        "\n\n请严格按照以下 JSON Schema 输出一个合法的 JSON 对象，"
        "用 ```json ... ``` 包裹，不要在 JSON 外添加任何说明文字：\n"
        f"```json\n{schema_str}\n```"
    )

    aug = list(messages)
    last = aug[-1]
    aug[-1] = HumanMessage(content=last.content + instruction)

    response = llm.invoke(aug)
    return _extract(response.content, output_class)


def _extract(text: str, output_class: Type[T]) -> T:
    """Extract and parse JSON from the LLM's reply."""
    # prefer a ```json ... ``` fenced block
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        return output_class.model_validate_json(m.group(1))

    # otherwise, the outermost { ... }
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        return output_class.model_validate_json(m.group(0))

    raise ValueError(f"LLM 回复中未找到有效 JSON，原文前 300 字：{text[:300]!r}")
