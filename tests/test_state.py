"""测试 CCAState 字段契约 + Annotated reducer 行为。"""
from __future__ import annotations

from operator import add

from cca.state import CCAState


REQUIRED_FIELDS = {
    "user_query",
    "target_product",
    "competitor_names",
    "task_plan",
    "analyst_task",
    "report_task",
    "profiles",
    "review_state",
    "qa_results",
    "report_status",
    "report_md",
    "report_pdf_path",
    "qa_notes",
    "audit_log",
}


def test_ccastate_has_all_expected_fields() -> None:
    assert set(CCAState.__annotations__.keys()) == REQUIRED_FIELDS


def test_ccastate_has_analyst_task_and_report_task() -> None:
    """D-018 阶段二/三 task 字段必须在 state 里。"""
    assert "analyst_task" in CCAState.__annotations__
    assert "report_task" in CCAState.__annotations__


def test_review_state_reducer_appends_not_replaces() -> None:
    """review_state 用 Annotated[list, add]，多次写入应累加。"""
    initial = [{"agent": "collector", "status": "passed"}]
    second = [{"agent": "insight", "status": "needs_retry"}]
    merged = add(initial, second)
    assert len(merged) == 2
    assert merged[0]["agent"] == "collector"
    assert merged[1]["agent"] == "insight"


def test_audit_log_reducer_accumulates_across_nodes() -> None:
    """audit_log 也是 add reducer，可被多节点并发追加。"""
    log_a = [{"node": "pm", "ts": "t1"}]
    log_b = [{"node": "collector", "ts": "t2"}]
    log_c = [{"node": "insight", "ts": "t3"}]
    merged = add(add(log_a, log_b), log_c)
    assert [e["node"] for e in merged] == ["pm", "collector", "insight"]


def test_qa_notes_reducer_appends_strings() -> None:
    """qa_notes 是 list[str]，add 应做字符串列表拼接。"""
    merged = add(["note1"], ["note2", "note3"])
    assert merged == ["note1", "note2", "note3"]
