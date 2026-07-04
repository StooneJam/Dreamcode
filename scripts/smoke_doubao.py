"""Smoke test for Doubao's three call modes -- run this first after setting CCA_DEV_MODEL_OVERRIDE=doubao.

Verifies Doubao's support for these three API behaviors, to decide whether the dev override is usable:
    1. function_calling with a simple schema -- used by PM's `_invoke_pm`
    2. tool calling -- used by Collector/Insight's create_react_agent
    3. function_calling with a nested schema -- debate's new path (after the D-040
       switch from json_object to function_calling)

If any of these fails, the current Doubao model id doesn't support that capability, and needs a different model or a fallback plan.

Usage:
    $env:PYTHONPATH="src"; $env:CCA_DEV_MODEL_OVERRIDE="doubao"
    python scripts/smoke_doubao.py
"""
from __future__ import annotations

import os
import sys
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field


def _hr(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}", flush=True)


def _ok(msg: str) -> None:
    print(f"  PASS · {msg}", flush=True)


def _fail(msg: str, err: Exception) -> None:
    print(f"  FAIL · {msg}\n    {type(err).__name__}: {err}", flush=True)


# ── 1. function_calling (PM's path) ───────────────────────────────────


class _PMOutput(BaseModel):
    """A slimmed-down simulation of PM phase 2's TaskPlanOutput."""
    competitors: list[str] = Field(min_length=1, description="Names of 3 leading competitors")
    rationale: str = Field(description="One paragraph explaining the selection")


def check_function_calling() -> bool:
    _hr("1/3 function_calling (PM's path)")
    from cca.llm.factory import gpt
    try:
        llm = gpt.with_structured_output(_PMOutput, method="function_calling")
        result = llm.invoke([
            SystemMessage(content="你是产品经理，要选竞品做分析。"),
            HumanMessage(content="目标产品是飞书。给我 3 家直接竞品 + 简要理由。"),
        ])
        assert isinstance(result, _PMOutput)
        assert len(result.competitors) >= 1
        _ok(f"competitors={result.competitors}")
        return True
    except Exception as e:
        _fail("with_structured_output(method='function_calling') 调用失败", e)
        return False


# ── 2. tool calling (Collector/Insight's ReAct path) ──────────────────


@tool
def echo_tool(text: str) -> str:
    """Return the input unchanged; used only to verify the LLM can correctly initiate a tool call."""
    return f"echoed: {text}"


def check_tool_calling() -> bool:
    _hr("2/3 tool calling (ReAct path)")
    from cca.llm.factory import deepseek
    try:
        agent = create_react_agent(model=deepseek, tools=[echo_tool])
        result = agent.invoke(
            {"messages": [HumanMessage(content="请调用 echo_tool，输入 'hello'，然后告诉我结果。")]},
            config={"recursion_limit": 6},
        )
        msgs = result.get("messages") or []
        tool_call_made = any(
            getattr(m, "tool_calls", None) for m in msgs
        )
        if tool_call_made:
            _ok(f"ReAct 完成 ({len(msgs)} messages)，至少一次 tool_call")
            return True
        _fail("LLM 全程未发起 tool_call", RuntimeError("no tool_calls in messages"))
        return False
    except Exception as e:
        _fail("create_react_agent 调用失败", e)
        return False


# ── 3. function_calling with a nested schema (debate's new path) ──────


class _DebateVerdictLike(BaseModel):
    """A simulation of debate's _phase_judge output's complex nested schema."""
    final_verdict: Literal["accepted", "rejected", "accepted_with_revision"] = Field(
        description="The final verdict",
    )
    judge_rationale: str = Field(description="One paragraph explaining the verdict")
    revised_output: dict = Field(
        default_factory=dict,
        description="The revised object if verdict=accepted_with_revision, otherwise empty",
    )


def check_debate_path() -> bool:
    _hr("3/3 function_calling with a nested schema (debate's new path)")
    from cca.llm.factory import doubao
    try:
        llm = doubao.with_structured_output(_DebateVerdictLike, method="function_calling")
        result = llm.invoke([
            SystemMessage(content="你是仲裁者。基于两辩方观点给出 final_verdict + 理由。"),
            HumanMessage(content=(
                "辩题：腾讯会议算不算飞书竞品？\n"
                "甲方：算（都属企业协作工具）。\n"
                "乙方：不算（腾讯会议是单点视频，飞书是一体化平台）。"
            )),
        ])
        assert isinstance(result, _DebateVerdictLike)
        assert result.final_verdict in ("accepted", "rejected", "accepted_with_revision")
        assert result.judge_rationale
        _ok(f"verdict={result.final_verdict}, rationale={result.judge_rationale[:60]}...")
        return True
    except Exception as e:
        _fail("with_structured_output(method='function_calling') 嵌套 schema 失败", e)
        return False


# ── main ──────────────────────────────────────────────────────────────


def main() -> int:
    override = os.getenv("CCA_DEV_MODEL_OVERRIDE", "").lower()
    if override != "doubao":
        print(
            "WARN: 当前未设 CCA_DEV_MODEL_OVERRIDE=doubao；"
            "本脚本仍会跑，但调用的是原家族模型而非 Doubao。",
            flush=True,
        )

    results: dict[str, bool] = {
        "function_calling": check_function_calling(),
        "tool_calling": check_tool_calling(),
        "debate_path": check_debate_path(),
    }

    _hr("SUMMARY")
    for name, ok in results.items():
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name}", flush=True)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
