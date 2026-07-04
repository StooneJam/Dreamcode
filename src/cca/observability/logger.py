"""Full-pipeline token audit: sums usage per model.

Two granularities, pick as needed:

Single pipeline (recommended, precise, works offline) -- wrap graph.invoke with
`track_pipeline_tokens()`.
    Boundary = this invoke's run tree (collect_runs scope), no LangSmith dependency
    and no DB-write latency. A LangSmith project is a flat run stream with no
    "start/end" concept -- the real boundary is the trace; this module reads
    straight from the local run tree, sidestepping the "which run was this" problem.

        with track_pipeline_tokens() as box:
            result = graph.invoke(state, config={"recursion_limit": 30})
        print(format_table(box["usages"]))

Live during a run (frontend display) -- attach `LiveTokenCounter` to the graph's
callbacks; it accumulates on every LLM call and can be read at any moment
(thread-safe, compatible with Send fanout's concurrency).

        counter = LiveTokenCounter()
        for step in graph.stream(state, config={"callbacks": [counter], "recursion_limit": 30}):
            push_to_frontend(counter.as_rows())   # updates as each agent finishes

Cross-project historical audit -- `aggregate_by_model()` / the CLI pulls from LangSmith.
    python -m cca.observability.logger                # last N runs project-wide
    python -m cca.observability.logger --latest-run   # the most recent pipeline (by trace)
    python -m cca.observability.logger --trace <id>

Doubao (Ark) shows up in LangSmith/metadata as its endpoint id (ep-...); mapped back
to "doubao" via .env's DOUBAO_MODEL. Cost doesn't rely on LangSmith's pricing table
(deepseek/doubao aren't in its built-in list) -- it's computed from config.yaml's
`observability.pricing`; unconfigured models just report tokens with no cost.
"""
from __future__ import annotations

import argparse
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Iterator

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langsmith import Client

from cca.settings import load_config


@dataclass
class ModelUsage:
    """Token totals for a single model over the selected scope."""

    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens

    @property
    def cost_usd(self) -> float | None:
        return _cost(self.model, self.input_tokens, self.output_tokens)


# ── model name / cost ───────────────────────────────────────────────────


def _model_alias() -> dict[str, str]:
    """Ark endpoint id -> friendly name. .env's DOUBAO_MODEL is that ep-... string."""
    ep = os.getenv("DOUBAO_MODEL")
    return {ep: "doubao"} if ep else {}


def _cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Compute cost from config.yaml observability.pricing's per-million-token (input, output) rate.

    Keys are matched as a lowercase substring of the model name; no config or no
    match returns None (report tokens only, don't guess at a price).
    """
    pricing = (load_config().get("observability") or {}).get("pricing") or {}
    name = model.lower()
    for key, price in pricing.items():
        if key.lower() in name:
            return round(input_tokens / 1e6 * float(price[0]) + output_tokens / 1e6 * float(price[1]), 6)
    return None


def _sorted(by_model: dict[str, ModelUsage]) -> list[ModelUsage]:
    return sorted(by_model.values(), key=lambda u: -u.total_tokens)


# ── single pipeline: aggregate the local run tree ───────────────────────


def _walk_llm_runs(run: Any) -> Iterator[Any]:
    """Depth-first yield of every llm node in the run tree (including nested ReAct subgraph calls)."""
    if getattr(run, "run_type", None) == "llm":
        yield run
    for child in getattr(run, "child_runs", None) or []:
        yield from _walk_llm_runs(child)


def _find_usage_metadata(node: Any) -> dict | None:
    """Recursively find the first usage_metadata in outputs (a field normalized across providers)."""
    if isinstance(node, dict):
        if node.get("usage_metadata"):
            return node["usage_metadata"]
        for value in node.values():
            if found := _find_usage_metadata(value):
                return found
    elif isinstance(node, list):
        for value in node:
            if found := _find_usage_metadata(value):
                return found
    return None


def _usage_of(run: Any) -> tuple[int, int, int]:
    """Get (input, output, total) from the local run.outputs. Prefers usage_metadata, falls back to token_usage."""
    outputs = getattr(run, "outputs", None) or {}
    if usage := _find_usage_metadata(outputs.get("generations")):
        return (
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("total_tokens", 0),
        )
    tk = (outputs.get("llm_output") or {}).get("token_usage") or {}
    return (tk.get("prompt_tokens", 0), tk.get("completion_tokens", 0), tk.get("total_tokens", 0))


def _model_of(run: Any) -> str:
    meta = (getattr(run, "extra", None) or {}).get("metadata") or {}
    out = getattr(run, "outputs", None) or {}
    return meta.get("ls_model_name") or (out.get("llm_output") or {}).get("model_name") or "(unknown)"


def aggregate_traced(traced_runs: list[Any]) -> list[ModelUsage]:
    """Sum tokens per model from the local run tree. traced_runs are the top-level runs collect_runs collected."""
    alias = _model_alias()
    by_model: dict[str, ModelUsage] = {}
    for root in traced_runs:
        for run in _walk_llm_runs(root):
            model = alias.get(_model_of(run), _model_of(run))
            by_model.setdefault(model, ModelUsage(model)).add(*_usage_of(run))
    return _sorted(by_model)


@contextmanager
def track_pipeline_tokens() -> Iterator[dict[str, Any]]:
    """Wrap a single graph.invoke; after the with-block, box['usages'] holds this
    run's per-model token totals.

    box['run_id'] is this trace's root run id (for looking up LangSmith details).
    The try/finally ensures box still gets filled if graph.invoke raises mid-way --
    that's exactly the scenario where you most need to look up the trace (a failed
    call), so the run_id can't be lost just because the with-block exited early.
    """
    from langchain_core.tracers.context import collect_runs

    box: dict[str, Any] = {}
    with collect_runs() as cb:
        try:
            yield box
        finally:
            box["usages"] = aggregate_traced(cb.traced_runs)
            box["run_id"] = str(cb.traced_runs[0].id) if cb.traced_runs else None


# ── live during a run: callback accumulator (frontend display) ─────────


def _usage_from_llm_result(response: LLMResult) -> tuple[int, int, int]:
    """Get (input, output, total) from on_llm_end's LLMResult. Prefers usage_metadata."""
    for gens in response.generations:
        for gen in gens:
            if usage := getattr(getattr(gen, "message", None), "usage_metadata", None):
                return (
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    usage.get("total_tokens", 0),
                )
    tk = (response.llm_output or {}).get("token_usage") or {}
    return (tk.get("prompt_tokens", 0), tk.get("completion_tokens", 0), tk.get("total_tokens", 0))


class LiveTokenCounter(BaseCallbackHandler):
    """Accumulates per-model tokens live during a run, for the frontend to poll.

    Attached to graph.invoke/stream's config["callbacks"], propagates into nested
    ReAct subgraph calls. The model name is only given in on_chat_model_start's
    metadata, so it's stashed by run_id until on_llm_end. Locked throughout, safe
    for Send fanout's concurrent writes. This audit callback never interrupts the
    main pipeline.
    """

    raise_error = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_model: dict[str, ModelUsage] = {}
        self._model_of: dict[Any, str] = {}

    def on_chat_model_start(
        self, serialized: dict, messages: list, *, run_id: Any,
        metadata: dict | None = None, **_: Any,
    ) -> None:
        with self._lock:
            self._model_of[run_id] = (metadata or {}).get("ls_model_name") or ""

    def on_llm_end(self, response: LLMResult, *, run_id: Any, **_: Any) -> None:
        with self._lock:
            name = self._model_of.pop(run_id, "")
        model = _model_alias().get(name, name) or "(unknown)"
        input_tokens, output_tokens, total_tokens = _usage_from_llm_result(response)
        with self._lock:
            self._by_model.setdefault(model, ModelUsage(model)).add(
                input_tokens, output_tokens, total_tokens
            )

    def on_llm_error(self, error: BaseException, *, run_id: Any, **_: Any) -> None:
        with self._lock:
            self._model_of.pop(run_id, None)

    def snapshot(self) -> list[ModelUsage]:
        """A copy of the current per-model totals (sorted by total desc), callable at any point during a run."""
        with self._lock:
            return _sorted({model: replace(usage) for model, usage in self._by_model.items()})

    def as_rows(self) -> list[dict[str, Any]]:
        """A frontend-friendly serializable snapshot (with cost)."""
        return [
            {
                "model": u.model, "calls": u.calls,
                "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                "total_tokens": u.total_tokens, "cost_usd": u.cost_usd,
            }
            for u in self.snapshot()
        ]

    def total_tokens(self) -> int:
        with self._lock:
            return sum(u.total_tokens for u in self._by_model.values())


# ── web link for a single run (frontend's "view full trace") ───────────


def resolve_trace_url(langsmith_run_id: str | None) -> str | None:
    """Best-effort return of a LangSmith run's web link. Returns None if tracing is
    off or the lookup fails.

    Needs one read_run network round-trip to get project info, so this is only
    called on-demand by the frontend, never on the job's hot path.
    """
    if not langsmith_run_id or os.getenv("LANGSMITH_TRACING", "").lower() not in ("true", "1"):
        return None
    try:
        client = Client()
        return client.get_run_url(run=client.read_run(langsmith_run_id))
    except Exception:
        return None


# ── cross-project history: pulled from LangSmith ────────────────────────


def _project() -> str:
    proj = os.getenv("LANGSMITH_PROJECT")
    if not proj:
        raise RuntimeError("LANGSMITH_PROJECT 未设置，无法定位项目")
    return proj


def _latest_trace_id(client: Client, project: str) -> str:
    root = next(client.list_runs(project_name=project, is_root=True, limit=1), None)
    if root is None:
        raise RuntimeError(f"项目 {project} 没有任何 run")
    return str(root.trace_id)


def aggregate_by_model(
    *, project: str | None = None, trace_id: str | None = None, cap: int | None = 300
) -> list[ModelUsage]:
    """Sum tokens per model from LangSmith (historical / cross-run audit)."""
    project = project or _project()
    client = Client()
    alias = _model_alias()
    kwargs: dict[str, Any] = {"project_name": project, "run_type": "llm"}
    if trace_id:
        kwargs["filter"] = f'eq(trace_id, "{trace_id}")'
    by_model: dict[str, ModelUsage] = {}
    for i, run in enumerate(client.list_runs(**kwargs)):
        if cap is not None and i >= cap:
            break
        meta = (run.extra or {}).get("metadata") or {}
        name = meta.get("ls_model_name") or "(unknown)"
        model = alias.get(name, name)
        by_model.setdefault(model, ModelUsage(model)).add(
            run.prompt_tokens or 0, run.completion_tokens or 0, run.total_tokens or 0
        )
    return _sorted(by_model)


# ── display ─────────────────────────────────────────────────────────────


def format_table(usages: list[ModelUsage]) -> str:
    """An aligned table + a total row."""
    lines = [f"{'model':28} {'calls':>6} {'input':>10} {'output':>10} {'total':>10} {'cost$':>10}"]
    tcalls = tin = tout = ttot = 0
    tcost = 0.0
    for u in usages:
        cost = u.cost_usd
        lines.append(
            f"{u.model:28} {u.calls:>6} {u.input_tokens:>10} {u.output_tokens:>10} "
            f"{u.total_tokens:>10} {('' if cost is None else f'{cost:.4f}'):>10}"
        )
        tcalls += u.calls
        tin += u.input_tokens
        tout += u.output_tokens
        ttot += u.total_tokens
        tcost += cost or 0.0
    lines.append(f"{'TOTAL':28} {tcalls:>6} {tin:>10} {tout:>10} {ttot:>10} {tcost:>10.4f}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="LangSmith token 消耗按模型加和（历史审计）")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--latest-run", action="store_true", help="只算最近一次完整 pipeline")
    scope.add_argument("--trace", type=str, default=None, help="指定 trace_id")
    p.add_argument("--project", type=str, default=None, help="LangSmith 项目，默认取 env")
    p.add_argument("--cap", type=int, default=300, help="全项目模式扫描的最大 run 数")
    args = p.parse_args()

    project = args.project or _project()
    trace_id = args.trace or (_latest_trace_id(Client(), project) if args.latest_run else None)

    scope_desc = f"trace {trace_id}" if trace_id else f"最近 {args.cap} 条 llm run"
    print(f"项目 {project} · {scope_desc} · 按模型加和\n")
    cap = None if trace_id else args.cap
    print(format_table(aggregate_by_model(project=project, trace_id=trace_id, cap=cap)))


if __name__ == "__main__":
    main()
