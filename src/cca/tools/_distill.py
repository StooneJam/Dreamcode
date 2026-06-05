"""网页正文 → 任务相关逐字片段的蒸馏。

fetch_url 在结果进入 ReAct history 之前把整页正文压成
若干逐字片段，避免原文在 history 里被每轮重发、膨胀 input。

逐字铁律：snippet 是下游 Evidence 的溯源原文，蒸馏只摘抄不改写（见 prompts/distill.md）。
失败降级：function_calling 偶发返 None（D-040）时不崩工具，原文当单条片段兜底（打 WARN 可见）。
"""
from __future__ import annotations

from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import get_llm

# 系统 prompt 进程级缓存：distill 调用很频繁，不每次读盘。
_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "distill.md").read_text(encoding="utf-8")


class _DistillOut(BaseModel):
    """蒸馏产出：若干从正文原样摘抄的相关片段。"""

    snippets: list[str] = Field(description="从正文逐字摘抄的相关片段，3-8 条；无相关内容则空列表")


def distill(text: str, focus: str) -> list[str]:
    """用 DeepSeek 槽从 text 原样摘抄与 focus 相关的逐字片段。

    function_calling 跨 DeepSeek / 豆包 override 都通用（json_mode 在豆包下不支持）。
    """
    llm = get_llm("deepseek").with_structured_output(_DistillOut, method="function_calling")
    result = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"关注点（focus）：{focus}\n\n正文：\n{text}"),
    ])
    if result is None:
        # function_calling 偶发不发 tool_call 返 None（D-040）。降级：不蒸了，原文当单条片段，
        # 保证工具不崩、形状不变（代价：这条不压缩）。打 WARN 让降级可见。
        print(f"  [distill] WARN: function_calling 返 None，降级用原文（focus={focus[:40]}）", flush=True)
        return [text]
    return cast(_DistillOut, result).snippets

