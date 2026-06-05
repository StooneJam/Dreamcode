"""网页正文 → 任务相关逐字片段的蒸馏。

fetch_url / web_search 在结果进入 ReAct history 之前调本模块，把整页正文压成
若干逐字片段，避免原文在 history 里被每轮重发、膨胀 input。

逐字铁律：snippet 是下游 Evidence 的溯源原文，蒸馏只摘抄不改写（见 prompts/distill.md）。
失败不降级：内容蒸馏本不该失败，真失败就让它 raise（用户决策，D-035 的有意例外）。
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
    result = cast(_DistillOut, llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"关注点（focus）：{focus}\n\n正文：\n{text}"),
    ]))
    return result.snippets


class _ResultSnippets(BaseModel):
    index: int = Field(description="对应输入结果的序号")
    snippets: list[str] = Field(description="该结果正文中与 focus 相关的逐字片段；无则空列表")


class _ResultsDistillOut(BaseModel):
    results: list[_ResultSnippets]


def distill_results(contents: list[str], focus: str) -> list[list[str]]:
    """一次 LLM 调用，对一批结果正文各自原样摘抄与 focus 相关的逐字片段。

    返回与 contents 等长的列表：contents[i] 的片段在返回值[i]（按 index 对齐，
    保住 web_search 结果的 url↔snippet 绑定，供下游 Evidence 溯源）。
    """
    llm = get_llm("deepseek").with_structured_output(_ResultsDistillOut, method="function_calling")
    blocks = "\n\n".join(f"【结果 {i}】\n{c}" for i, c in enumerate(contents))
    out = cast(_ResultsDistillOut, llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"关注点（focus）：{focus}\n\n"
            f"下面是 {len(contents)} 条结果正文（按【结果 N】编号）。对每条，从它正文里原样"
            f"摘抄与 focus 相关的逐字片段，按 index 返回；无相关内容的 snippets 留空。\n\n{blocks}"
        )),
    ]))
    by_index = {r.index: r.snippets for r in out.results}
    return [by_index.get(i, []) for i in range(len(contents))]
