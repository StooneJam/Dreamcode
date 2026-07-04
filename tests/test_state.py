"""Tests for CCAState's field contract + Annotated reducer behavior."""
from __future__ import annotations

from functools import reduce
from operator import add

from cca.state import CCAState, _merge_profiles

REQUIRED_FIELDS = {
    "user_query",
    "target_product",
    "report_language",       # report output language "zh" | "en", defaults to "zh"
    "user_files",            # file paths written by the upload mechanism
    "initial_brief",         # PM phase 1's output
    "domain_seed",           # PM phase 1's document-distillation output
    "exploration_result",    # Collector's round-one exploration output
    "competitor_names",
    "task_plan",             # PM phase 2
    "report_task",           # PM phase 3 (includes the old AnalystTask fields, Reporter's internal analysis)
    "profiles",
    "review_state",
    "reroute_count",         # cumulative PM review -> handle_signal reroute count; escalates to forced at 2 to prevent infinite loops
    "human_review_feedback", # phase 2.5's one-shot free-text user revision feedback
    "human_review_done",     # gate interrupt: pauses to collect feedback only once
    "human_feedback_consumed",  # gate review adoption: feedback only factors into one review round
    "qa_results",
    "report_status",
    "report_md",
    "report_pdf_path",
    "analysis_start_ts",     # written at the graph's entry, used at END to compute elapsed time
    "analysis_end_ts",       # written by report_node
    "qa_notes",
    "audit_log",
    "debate_results",        # accumulated across phases by the debate skill
    "agent_signals",         # the back-channel
    "consumed_signal_ids",   # PM's consumption dedup pointer
    "decision_log",          # PM's decision records, backing offline Q&A
}


def test_ccastate_has_all_expected_fields() -> None:
    assert set(CCAState.__annotations__.keys()) == REQUIRED_FIELDS


def test_ccastate_has_task_plan_and_report_task() -> None:
    """The phase 2/3 task fields must be in state; analyst_task has been folded into report_task."""
    assert "task_plan" in CCAState.__annotations__
    assert "report_task" in CCAState.__annotations__
    assert "analyst_task" not in CCAState.__annotations__


def test_review_state_reducer_appends_not_replaces() -> None:
    """review_state uses Annotated[list, add], so multiple writes should accumulate."""
    initial = [{"agent": "collector", "status": "passed"}]
    second = [{"agent": "insight", "status": "needs_retry"}]
    merged = add(initial, second)
    assert len(merged) == 2
    assert merged[0]["agent"] == "collector"
    assert merged[1]["agent"] == "insight"


def test_audit_log_reducer_accumulates_across_nodes() -> None:
    """audit_log is also an add reducer, appendable concurrently by multiple nodes."""
    log_a = [{"node": "pm", "ts": "t1"}]
    log_b = [{"node": "collector", "ts": "t2"}]
    log_c = [{"node": "insight", "ts": "t3"}]
    merged = add(add(log_a, log_b), log_c)
    assert [e["node"] for e in merged] == ["pm", "collector", "insight"]


def test_qa_notes_reducer_appends_strings() -> None:
    """qa_notes is list[str]; add should concatenate the string lists."""
    merged = add(["note1"], ["note2", "note3"])
    assert merged == ["note1", "note2", "note3"]


# ── _merge_profiles: fanout concurrency safety (an empty value never overwrites real data) ──

_FULL = {"瑞幸": {"product_name": "瑞幸",
                  "dimensions": [{"name": "门店"}], "sources": ["url1"]}}
# _skip_result's crash placeholder: has empty dimensions/sources, must never overwrite collector's real data on the same key
_EMPTY_SHELL = {"瑞幸": {"product_name": "瑞幸", "company": None,
                        "dimensions": [], "sources": []}}


def test_merge_profiles_empty_list_never_clobbers_populated() -> None:
    """An empty [] must not overwrite already-filled dimensions/sources -- this
    failing means the P0 regression of a placeholder blanking out collector's real
    data has come back."""
    merged = _merge_profiles(_FULL, _EMPTY_SHELL)
    assert merged["瑞幸"]["dimensions"] == [{"name": "门店"}]
    assert merged["瑞幸"]["sources"] == ["url1"]


def test_merge_profiles_clobber_is_fold_order_independent() -> None:
    """Regardless of whether collector(full) or the crashed worker(shell) folds first, real data is retained."""
    full_then_shell = reduce(_merge_profiles, [_FULL, _EMPTY_SHELL], {})
    shell_then_full = reduce(_merge_profiles, [_EMPTY_SHELL, _FULL], {})
    assert full_then_shell == shell_then_full
    assert full_then_shell["瑞幸"]["dimensions"] == [{"name": "门店"}]


def test_merge_profiles_none_does_not_clobber() -> None:
    """Preserve the original contract: a right-side None doesn't overwrite an
    existing left-side value (prevents a second round from clearing sentiment)."""
    left = {"A": {"sentiment": {"score": 0.8}}}
    right = {"A": {"sentiment": None}}
    assert _merge_profiles(left, right)["A"]["sentiment"] == {"score": 0.8}


def test_merge_profiles_nonempty_overwrites() -> None:
    """A non-empty incoming value still follows "latest overwrites," and 0/False aren't treated as empty and dropped."""
    left = {"A": {"dimensions": [{"name": "旧"}], "flag": True, "n": 5}}
    right = {"A": {"dimensions": [{"name": "新"}], "flag": False, "n": 0}}
    out = _merge_profiles(left, right)["A"]
    assert out["dimensions"] == [{"name": "新"}]
    assert out["flag"] is False
    assert out["n"] == 0


def test_merge_profiles_cross_agent_fields_coexist() -> None:
    """collector (dimensions/sources) and insight (sentiment) each write their own fields on the same key, without dropping the other's."""
    collector = {"A": {"product_name": "A", "dimensions": [{"name": "d"}], "sources": ["u"]}}
    insight = {"A": {"sentiment": {"score": 0.9}}}
    out = reduce(_merge_profiles, [collector, insight], {})["A"]
    assert out["dimensions"] == [{"name": "d"}]
    assert out["sentiment"] == {"score": 0.9}


def test_merge_profiles_disjoint_keys_both_kept() -> None:
    merged = _merge_profiles({"A": {"x": 1}}, {"B": {"y": 2}})
    assert merged == {"A": {"x": 1}, "B": {"y": 2}}
