"""ReAct agent streaming helper + per-node cache hook.

`stream_react(agent, messages, label, cache_key=...)` dispatches on CCA_CACHE_MODE:
    off/write : agent.stream, print each step inline; write mode persists cache after
    replay    : skip the LLM, print the cached messages list directly (instant)
    auto      : try cache first; on miss, stream + write

cache_key=None always skips the cache path (same as no hook).

Print format:
    [Collector] start (recursion_limit=40)
    [Collector] thinking: ...
    [Collector] call web_search({"query": "..."})
    [Collector] ret finalize_exploration (628B) {"target_product":"..."...
    [Collector] done (8 messages)
    [Collector] (cache replay)         # only on replay/auto hit

Falls back to agent.invoke if a MagicMock's .stream doesn't yield dicts (test scenario).
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

# Set by the server around graph.invoke so each log line also reaches the SSE queue.
_sse_emit: ContextVar[Callable[[dict], None] | None] = ContextVar("cca_sse_emit", default=None)


class JobCancelled(RuntimeError):
    """Raised by emit_fn to abort graph execution between nodes (client disconnected)."""


@contextmanager
def set_sse_emitter(fn: Callable[[dict], None]):
    """Stream all logs to the SSE queue within this with-block. fn must be thread-safe."""
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
        except JobCancelled:
            raise  # let cancellation propagate and stop further LLM calls
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
    # thinking/call/ret events are emitted by _print_message; this is the generic log path
    if not (line.startswith("thinking:") or line.startswith("call ") or line.startswith("ret ")):
        _emit({"type": "log", "agent": label, "text": line})


def _print_message(msg: Any, label: str) -> None:
    """AIMessage/ToolMessage -> short summary + structured SSE event."""
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
    """agent.stream(values); raise if a non-dict chunk is yielded so the caller can fall back."""
    chunks = agent.stream(
        {"messages": messages},
        config={"recursion_limit": recursion_limit},
        stream_mode="values",
    )
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError(f"stream yielded non-dict {type(chunk).__name__}")
        yield chunk


def _cache_read_tokens(msg: AIMessage) -> int:
    """Cache-hit input tokens. OpenAI/Doubao use input_token_details.cache_read,
    DeepSeek uses response_metadata.token_usage.prompt_cache_hit_tokens; else 0."""
    meta = getattr(msg, "usage_metadata", None) or {}
    hit = (meta.get("input_token_details") or {}).get("cache_read")
    if hit is None:
        rm = getattr(msg, "response_metadata", None) or {}
        hit = (rm.get("token_usage") or {}).get("prompt_cache_hit_tokens")
    return hit or 0


def _sum_usage(messages: list) -> dict[str, int]:
    inp = out = cached = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            meta = getattr(msg, "usage_metadata", None) or {}
            inp += meta.get("input_tokens", 0)
            out += meta.get("output_tokens", 0)
            cached += _cache_read_tokens(msg)
    return {"input": inp, "output": out, "cached": cached, "total": inp + out}


def _run_real(agent: Any, messages: list, label: str, recursion_limit: int) -> list:
    """Run ReAct for real: prefer .stream, fall back to .invoke on failure."""
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
        # hit the step limit: return what we collected, don't abort the whole pipeline
        _print(label, f"WARN: recursion_limit={recursion_limit} reached, returning partial output")
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
    """LangChain message -> JSON string (preserves type info via langchain_core.load.dump)."""
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
    """Stream a ReAct agent run. With cache_key + cache_node, dispatches on CCA_CACHE_MODE.

    Returns the final messages list (equivalent to agent.invoke()["messages"]).
    """
    mode = react_cache.get_mode()
    use_cache = cache_key is not None and cache_node is not None

    # -- replay / auto: try a cache hit --
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
                f"[react_cache] mode=replay but cache missed: node={cache_node} "
                f"key={react_cache.hash_key(cache_key)}. Run with mode=write first."
            )

    # -- real run path --
    _print(label, f"start (recursion_limit={recursion_limit})")
    sys.stdout.flush()
    final_messages = _run_real(agent, messages, label, recursion_limit)
    _print(label, f"done ({len(final_messages)} messages)")

    usage = _sum_usage(final_messages)
    if usage["total"] > 0:
        _print(
            label,
            f"tokens: in={usage['input']} (cached={usage['cached']}) "
            f"out={usage['output']} total={usage['total']}",
        )
        _emit({"type": "token_usage", "agent": label, **usage})

    # -- write / auto: persist cache --
    if use_cache and mode in ("write", "auto"):
        react_cache.put(cache_node, cache_key, {
            "messages_json": _serialize_messages(final_messages),
            "label": label,
        })
        _print(label, "(cache write)")

    return final_messages
