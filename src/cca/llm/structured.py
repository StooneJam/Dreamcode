"""LLM 结构化输出兼容层 —— 兼容不支持 tool_choice / response_format 的推理模型。

用法（替代 llm.with_structured_output(MyModel)）：
    from cca.llm.structured import invoke_structured
    result = invoke_structured(deepseek, messages, MyModel)

原理：
    把 JSON Schema 追加到最后一条 HumanMessage，要求模型输出合法 JSON；
    用正则从回复文本中提取 JSON 块并用 Pydantic 解析。
    不依赖 response_format / tool_choice，兼容所有 DeepSeek 模型包括推理版。
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
    """调用 LLM，将响应解析为指定 Pydantic 模型。"""
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
    """从 LLM 回复中提取 JSON 并解析。"""
    # 优先匹配 ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        return output_class.model_validate_json(m.group(1))

    # 其次匹配最外层 { ... }
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        return output_class.model_validate_json(m.group(0))

    raise ValueError(f"LLM 回复中未找到有效 JSON，原文前 300 字：{text[:300]!r}")
