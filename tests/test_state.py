"""测试 CompetitiveAnalysisState 的 reducers 行为。

Day 1 时仅占位，等 src/cca/state.py 落地后填实。
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="state.py 尚未实现，5.20 hello_world 后补")
def test_raw_sources_reducer_appends_not_replaces():
    """raw_sources 用 Annotated[list, add] reducer，多节点写入应累加。"""
    pass


@pytest.mark.skip(reason="state.py 尚未实现")
def test_retry_count_per_checkpoint_isolated():
    """retry_count 按 checkpoint 名隔离，QA 各阶段独立计数。"""
    pass
