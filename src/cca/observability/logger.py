"""全流程 token 消耗审计：按模型分别加和。

两种粒度，按需求选：

单次 pipeline（推荐，精确、离线可用）——用 `track_pipeline_tokens()` 包住 graph.invoke。
    边界 = 这一次 invoke 的 run 树（collect_runs 作用域），不依赖 LangSmith，也无入库
    延迟。LangSmith 项目里是一条扁平 run 流、没有“开始/结束”概念，真正的边界是 trace；
    本模块直接从本地 run 树取，规避了“分不清一次跑”的问题。

        with track_pipeline_tokens() as box:
            result = graph.invoke(state, config={"recursion_limit": 30})
        print(format_table(box["usages"]))

运行中实时（前端展示）——`LiveTokenCounter` 挂到 graph 的 callbacks，每次 LLM 调用
即时累加，任意时刻可读当前快照（线程安全，兼容 Send fanout 并行）。

        counter = LiveTokenCounter()
        for step in graph.stream(state, config={"callbacks": [counter], "recursion_limit": 30}):
            push_to_frontend(counter.as_rows())   # 随各 Agent 完成跳动

跨项目历史审计——`aggregate_by_model()` / CLI 从 LangSmith 拉。
    python -m cca.observability.logger                # 全项目最近 N 条
    python -m cca.observability.logger --latest-run   # 最近一次 pipeline（按 trace）
    python -m cca.observability.logger --trace <id>

豆包（Ark）在 LangSmith / metadata 里以端点 ID（ep-...）作模型名，按 .env 的
DOUBAO_MODEL 映射回 "doubao"。cost 不依赖 LangSmith 价表（deepseek/doubao 不在其内置
表里），按 config.yaml `observability.pricing` 自算；无配置则留空只报 token。
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
    """单个模型在选定范围内的 token 加和。"""

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


# ── 模型名 / 成本 ────────────────────────────────────────────────────────


def _model_alias() -> dict[str, str]:
    """Ark 端点 ID → 友好名。.env 的 DOUBAO_MODEL 即那串 ep-...。"""
    ep = os.getenv("DOUBAO_MODEL")
    return {ep: "doubao"} if ep else {}


def _cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """按 config.yaml observability.pricing 的每百万 token (输入,输出) 单价算成本。

    键按模型名子串小写匹配；无配置或无匹配返回 None（只报 token，不瞎猜价）。
    """
    pricing = (load_config().get("observability") or {}).get("pricing") or {}
    name = model.lower()
    for key, price in pricing.items():
        if key.lower() in name:
            return round(input_tokens / 1e6 * float(price[0]) + output_tokens / 1e6 * float(price[1]), 6)
    return None


def _sorted(by_model: dict[str, ModelUsage]) -> list[ModelUsage]:
    return sorted(by_model.values(), key=lambda u: -u.total_tokens)


# ── 单次 pipeline：本地 run 树聚合 ────────────────────────────────────────


def _walk_llm_runs(run: Any) -> Iterator[Any]:
    """深度优先 yield run 树里所有 llm 节点（含 ReAct 子图内部调用）。"""
    if getattr(run, "run_type", None) == "llm":
        yield run
    for child in getattr(run, "child_runs", None) or []:
        yield from _walk_llm_runs(child)


def _find_usage_metadata(node: Any) -> dict | None:
    """在 outputs 里递归找第一个 usage_metadata（跨 provider 归一字段）。"""
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
    """从本地 run.outputs 取 (input, output, total)。优先 usage_metadata，回落 token_usage。"""
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
    """从本地 run 树按模型加和。traced_runs 为 collect_runs 收集的顶层 run。"""
    alias = _model_alias()
    by_model: dict[str, ModelUsage] = {}
    for root in traced_runs:
        for run in _walk_llm_runs(root):
            model = alias.get(_model_of(run), _model_of(run))
            by_model.setdefault(model, ModelUsage(model)).add(*_usage_of(run))
    return _sorted(by_model)


@contextmanager
def track_pipeline_tokens() -> Iterator[dict[str, Any]]:
    """包住一次 graph.invoke；with 块结束后 box['usages'] 是本次各模型 token 加和。

    box['run_id'] 是本次 trace 的 root run id（供回查 LangSmith 详情）。
    """
    from langchain_core.tracers.context import collect_runs

    box: dict[str, Any] = {}
    with collect_runs() as cb:
        yield box
    box["usages"] = aggregate_traced(cb.traced_runs)
    box["run_id"] = str(cb.traced_runs[0].id) if cb.traced_runs else None


# ── 运行中实时：回调累加器（前端展示）──────────────────────────────────


def _usage_from_llm_result(response: LLMResult) -> tuple[int, int, int]:
    """从 on_llm_end 的 LLMResult 取 (input, output, total)。优先 usage_metadata。"""
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
    """运行中实时累加各模型 token，供前端轮询展示。

    挂到 graph.invoke/stream 的 config["callbacks"]，会传播到 ReAct 子图内部调用。
    model 名只在 on_chat_model_start 的 metadata 里给，故按 run_id 暂存到 on_llm_end。
    全程加锁，兼容 Send fanout 的并行写。审计回调永不打断主流程。
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
        """当前各模型加和的拷贝（按 total 降序），可在运行中任意时刻调用。"""
        with self._lock:
            return _sorted({model: replace(usage) for model, usage in self._by_model.items()})

    def as_rows(self) -> list[dict[str, Any]]:
        """前端友好的可序列化快照（含 cost）。"""
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


# ── 跨项目历史：从 LangSmith 拉 ───────────────────────────────────────────


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
    """从 LangSmith 按模型加和 token（历史 / 跨次审计）。"""
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


# ── 展示 ─────────────────────────────────────────────────────────────────


def format_table(usages: list[ModelUsage]) -> str:
    """对齐表格 + 合计行。"""
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
