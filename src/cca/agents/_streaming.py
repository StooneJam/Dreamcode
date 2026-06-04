"""ReAct agent 流式执行 helper + 节点级 cache hook。

`stream_react(agent, messages, label, cache_key=...)` 三种行为，按 CCA_CACHE_MODE 派发：
    off/write : 走 agent.stream，逐 step inline 打印；write 模式跑完后写缓存
    replay    : 跳过 LLM，从缓存读 messages list 直接逐条打印（秒级）
    auto      : 先查缓存命中即重放；未命中走 stream + 写缓存

若 cache_key=None 则永不走缓存路径，跟无 hook 版本一样。

打印格式：
    [Collector] start (recursion_limit=40)
    [Collector] thinking: ...
    [Collector] call web_search({"query": "钉钉 官网"})
    [Collector] ret finalize_exploration (628B) {"target_product":"飞书"...
    [Collector] done (8 messages)
    [Collector] (cache replay)         # 仅 replay/auto 命中时

若 MagicMock 的 .stream 返不出 dict（测试场景），自动 fallback 到 agent.invoke。
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.load.dump import dumps as lc_dumps
from langchain_core.load.load import loads as lc_loads

from cca.memory import react_cache

_THINKING_PREVIEW = 120
_TOOL_ARG_PREVIEW = 180
_TOOL_RESP_PREVIEW = 80

# 服务器层在 graph.invoke 外层设置此 contextvar，让每条日志同时推到 SSE 队列。
_sse_emit: ContextVar[Callable[[dict], None] | None] = ContextVar("cca_sse_emit", default=None)


@contextmanager
def set_sse_emitter(fn: Callable[[dict], None]):
    """在 with 块内把所有流式日志也发往 SSE 队列。fn 必须是线程安全的。"""
    token = _sse_emit.set(fn)
    try:
        yield
    finally:
        _sse_emit.reset(token)


def _emit(event: dict) -> None:
    fn = _sse_emit.get()
    if fn is not None:
        try:
            fn(event)
        except Exception:
            pass


def emit_sse(event: dict) -> None:
    """Push a structured SSE event from any agent or skill."""
    _emit(event)


def _short(text: str, n: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "..."


def _print(label: str, line: str) -> None:
    print(f"  [{label}] {line}", flush=True)
    # thinking / call / ret 由 _print_message 发结构化事件，这里只发通用 log
    if not (line.startswith("thinking:") or line.startswith("call ") or line.startswith("ret ")):
        _emit({"type": "log", "agent": label, "text": line})


def _print_message(msg: Any, label: str) -> None:
    """AIMessage / ToolMessage → 简短摘要 + SSE 结构化事件。"""
    if isinstance(msg, AIMessage):
        if tool_calls := getattr(msg, "tool_calls", None):
            for tc in tool_calls:
                args_str = json.dumps(tc.get("args", {}), ensure_ascii=False)
                short_args = _short(args_str, _TOOL_ARG_PREVIEW)
                _print(label, f"call {tc['name']}({short_args})")
                _emit({"type": "tool_call", "agent": label, "tool": tc["name"], "args": short_args})
        elif content := (msg.content or "").strip():
            _print(label, f"thinking: {_short(content, _THINKING_PREVIEW)}")
            _emit({"type": "thinking"})
    elif isinstance(msg, ToolMessage):
        size = len(msg.content or "")
        preview = _short(msg.content or "", _TOOL_RESP_PREVIEW)
        _print(label, f"ret {msg.name} ({size}B) {preview}")
        _emit({"type": "tool_result", "agent": label, "tool": msg.name,
               "size": f"{size}B", "preview": preview})


def _stream_iter(agent: Any, messages: list, recursion_limit: int):
    """agent.stream(values)；yield 非 dict 则 raise 让上层 fallback。"""
    chunks = agent.stream(
        {"messages": messages},
        config={"recursion_limit": recursion_limit},
        stream_mode="values",
    )
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError(f"stream yielded non-dict {type(chunk).__name__}")
        yield chunk


def _sum_usage(messages: list) -> dict[str, int]:
    inp = out = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            meta = getattr(msg, "usage_metadata", None) or {}
            inp += meta.get("input_tokens", 0)
            out += meta.get("output_tokens", 0)
    return {"input": inp, "output": out, "total": inp + out}


def _run_real(agent: Any, messages: list, label: str, recursion_limit: int) -> list:
    """真跑 ReAct：优先 .stream，失败 fallback .invoke。"""
    from langgraph.errors import GraphRecursionError
    seen = 0
    final_messages: list = []
    got_any_chunk = False
    try:
        for chunk in _stream_iter(agent, messages, recursion_limit):
            got_any_chunk = True
            msgs = chunk.get("messages") or []
            for msg in msgs[seen:]:
                _print_message(msg, label)
            seen = len(msgs)
            final_messages = msgs
    except GraphRecursionError:
        # 撞步数上限：返回已收集到的 messages，不中断整体流程
        _print(label, f"WARN: recursion_limit={recursion_limit} reached，返回已有产出")
        got_any_chunk = bool(final_messages)
    except (AttributeError, TypeError):
        got_any_chunk = False

    if not got_any_chunk:
        result = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": recursion_limit},
        )
        final_messages = (result or {}).get("messages") or []
        for msg in final_messages:
            _print_message(msg, label)

    return final_messages


def _serialize_messages(messages: list) -> str:
    """LangChain message → JSON 串（保留类型信息，用 langchain_core.load.dump）。"""
    return lc_dumps(messages)


def _deserialize_messages(payload: str) -> list:
    return lc_loads(payload)


def stream_react(
    agent: Any,
    messages: list,
    label: str,
    *,
    recursion_limit: int = 40,
    cache_key: dict | None = None,
    cache_node: str | None = None,
) -> list:
    """流式跑 ReAct agent。提供 cache_key + cache_node 时按 CCA_CACHE_MODE 走 cache 分支。

    返回最终 messages 列表（与 agent.invoke()["messages"] 等价）。
    """
    mode = react_cache.get_mode()
    use_cache = cache_key is not None and cache_node is not None

    # ── replay / auto 命中尝试 ──
    if use_cache and mode in ("replay", "auto"):
        cached = react_cache.get(cache_node, cache_key)
        if cached is not None:
            messages_list = _deserialize_messages(cached["messages_json"])
            _print(label, f"start (cache replay, {len(messages_list)} messages)")
            sys.stdout.flush()
            for msg in messages_list:
                _print_message(msg, label)
            _print(label, f"done ({len(messages_list)} messages) [cached]")
            return messages_list
        if mode == "replay":
            raise RuntimeError(
                f"[react_cache] mode=replay 但缓存未命中：node={cache_node} "
                f"key={react_cache.hash_key(cache_key)}。请先用 mode=write 跑一次。"
            )

    # ── 真跑路径 ──
    _print(label, f"start (recursion_limit={recursion_limit})")
    sys.stdout.flush()
    final_messages = _run_real(agent, messages, label, recursion_limit)
    _print(label, f"done ({len(final_messages)} messages)")

    usage = _sum_usage(final_messages)
    if usage["total"] > 0:
        _print(label, f"tokens: in={usage['input']} out={usage['output']} total={usage['total']}")
        _emit({"type": "token_usage", "agent": label, **usage})

    # ── write / auto 写缓存 ──
    if use_cache and mode in ("write", "auto"):
        react_cache.put(cache_node, cache_key, {
            "messages_json": _serialize_messages(final_messages),
            "label": label,
        })
        _print(label, "(cache write)")

    return final_messages
