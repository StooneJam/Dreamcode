"""observability.logger 聚合逻辑单测 —— 不打真 LangSmith。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from cca.observability import logger


# ── LangSmith 历史聚合（aggregate_by_model）──────────────────────────────


def _ls_run(model: str, prompt: int, completion: int) -> SimpleNamespace:
    """伪造一条 LangSmith llm Run（服务端字段已算好 token）。"""
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        extra={"metadata": {"ls_model_name": model}},
    )


class _FakeClient:
    def __init__(self, runs: list) -> None:
        self._runs = runs

    def list_runs(self, **_kwargs):
        return iter(self._runs)


@pytest.fixture
def patch_client(monkeypatch):
    def _install(runs: list) -> None:
        monkeypatch.setattr(logger, "Client", lambda: _FakeClient(runs))
    return _install


def test_aggregate_sums_tokens_per_model(patch_client):
    patch_client([
        _ls_run("deepseek-v4-pro", 10, 2),
        _ls_run("deepseek-v4-pro", 5, 3),
        _ls_run("gpt-5", 100, 50),
    ])
    by = {u.model: u for u in logger.aggregate_by_model(project="p")}
    assert by["deepseek-v4-pro"].calls == 2
    assert by["deepseek-v4-pro"].total_tokens == 20
    assert by["gpt-5"].total_tokens == 150


def test_aggregate_sorted_by_total_desc(patch_client):
    patch_client([_ls_run("small", 1, 1), _ls_run("big", 500, 500)])
    assert [u.model for u in logger.aggregate_by_model(project="p")] == ["big", "small"]


def test_doubao_endpoint_id_aliased(patch_client, monkeypatch):
    monkeypatch.setenv("DOUBAO_MODEL", "ep-20260514-xyz")
    patch_client([_ls_run("ep-20260514-xyz", 8, 4)])
    assert logger.aggregate_by_model(project="p")[0].model == "doubao"


# ── 单次 pipeline 本地 run 树聚合（aggregate_traced）─────────────────────


def _local_llm_run(model: str, inp: int, out: int, children: list | None = None) -> SimpleNamespace:
    """伪造本地 run 树节点：usage 藏在 outputs.generations[*].message.kwargs。"""
    msg = {"kwargs": {"usage_metadata": {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}}}
    return SimpleNamespace(
        id="run-id",
        run_type="llm",
        extra={"metadata": {"ls_model_name": model}},
        outputs={"generations": [[{"message": msg}]]},
        child_runs=children or [],
    )


def _chain_run(children: list) -> SimpleNamespace:
    return SimpleNamespace(id="root-id", run_type="chain", extra={}, outputs={}, child_runs=children)


def test_traced_walks_nested_llm_runs():
    # 一个 chain root 套两层 llm，模拟 ReAct 子图内部调用
    inner = _local_llm_run("deepseek-v4-pro", 30, 5)
    outer = _local_llm_run("deepseek-v4-pro", 10, 2, children=[inner])
    root = _chain_run([outer, _local_llm_run("gpt-5", 100, 40)])
    by = {u.model: u for u in logger.aggregate_traced([root])}
    assert by["deepseek-v4-pro"].calls == 2
    assert by["deepseek-v4-pro"].total_tokens == 47
    assert by["gpt-5"].total_tokens == 140


def test_traced_falls_back_to_llm_output_token_usage():
    run = SimpleNamespace(
        id="x", run_type="llm", extra={"metadata": {"ls_model_name": "gpt-5"}},
        outputs={"llm_output": {"token_usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}},
        child_runs=[],
    )
    usages = logger.aggregate_traced([run])
    assert usages[0].total_tokens == 10


# ── 实时累加器（LiveTokenCounter）────────────────────────────────────────


def _llm_result(inp: int, out: int) -> SimpleNamespace:
    """伪造 on_llm_end 的 LLMResult：usage_metadata 挂在 generation.message 上。"""
    msg = SimpleNamespace(usage_metadata={"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out})
    return SimpleNamespace(generations=[[SimpleNamespace(message=msg)]], llm_output={})


def _emit(counter, run_id, model, inp, out):
    counter.on_chat_model_start({}, [], run_id=run_id, metadata={"ls_model_name": model})
    counter.on_llm_end(_llm_result(inp, out), run_id=run_id)


def test_live_counter_accumulates_across_calls():
    c = logger.LiveTokenCounter()
    _emit(c, "r1", "deepseek-v4-pro", 10, 2)
    _emit(c, "r2", "deepseek-v4-pro", 5, 3)
    _emit(c, "r3", "gpt-5", 100, 40)
    rows = {r["model"]: r for r in c.as_rows()}
    assert rows["deepseek-v4-pro"]["total_tokens"] == 20
    assert rows["deepseek-v4-pro"]["calls"] == 2
    assert rows["gpt-5"]["total_tokens"] == 140
    assert c.total_tokens() == 160


def test_live_counter_readable_mid_run():
    c = logger.LiveTokenCounter()
    _emit(c, "r1", "gpt-5", 10, 5)
    assert c.total_tokens() == 15          # 运行中即可读
    _emit(c, "r2", "gpt-5", 20, 10)
    assert c.total_tokens() == 45          # 后续调用持续累加


def test_live_counter_aliases_doubao(monkeypatch):
    monkeypatch.setenv("DOUBAO_MODEL", "ep-abc")
    c = logger.LiveTokenCounter()
    _emit(c, "r1", "ep-abc", 8, 4)
    assert c.snapshot()[0].model == "doubao"


def test_live_counter_snapshot_is_copy():
    c = logger.LiveTokenCounter()
    _emit(c, "r1", "gpt-5", 10, 5)
    snap = c.snapshot()[0]
    snap.total_tokens = 99999              # 改快照不应回写内部状态
    assert c.total_tokens() == 15


# ── 成本 / 展示 ──────────────────────────────────────────────────────────


def test_cost_none_without_pricing(monkeypatch):
    monkeypatch.setattr(logger, "load_config", lambda: {})
    assert logger._cost("deepseek-v4-pro", 1_000_000, 1_000_000) is None


def test_cost_computed_from_pricing(monkeypatch):
    monkeypatch.setattr(
        logger, "load_config",
        lambda: {"observability": {"pricing": {"deepseek": [0.28, 0.42]}}},
    )
    assert logger._cost("deepseek-v4-pro", 1_000_000, 1_000_000) == 0.7


def test_format_table_has_total_row(patch_client):
    patch_client([_ls_run("gpt-5", 10, 5)])
    table = logger.format_table(logger.aggregate_by_model(project="p"))
    assert "TOTAL" in table
    assert "gpt-5" in table
