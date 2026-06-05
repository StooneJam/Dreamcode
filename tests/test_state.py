"""测试 CCAState 字段契约 + Annotated reducer 行为。"""
from __future__ import annotations

from functools import reduce
from operator import add

from cca.state import CCAState, _merge_profiles

REQUIRED_FIELDS = {
    "user_query",
    "target_product",
    "report_language",       # 报告输出语言 "zh" | "en"，默认 "zh"
    "user_files",            # 上传机制写入的文件路径列表
    "initial_brief",         # PM 阶段一产物
    "domain_seed",           # PM phase 1 文档蒸馏产物
    "exploration_result",    # Collector 一轮探索产物
    "competitor_names",
    "task_plan",             # PM 阶段二
    "report_task",           # PM 阶段三（含原 AnalystTask 字段，Reporter 内部分析）
    "profiles",
    "review_state",
    "reroute_count",         # PM review → handle_signal reroute 累计次数，达 2 时升 forced 防死循环
    "human_review_feedback", # 阶段 2.5 用户一次性自由文本修订意见
    "human_review_done",     # gate interrupt：只暂停收集一次
    "human_feedback_consumed",  # gate review 采纳：feedback 只参与一次评审判定
    "qa_results",
    "report_status",
    "report_md",
    "report_pdf_path",
    "analysis_start_ts",     # 图入口写入，END 汇总算耗时
    "analysis_end_ts",       # report_node 写入
    "qa_notes",
    "audit_log",
    "debate_results",        # debate skill 跨阶段累加
    "agent_signals",         # 反向通道
    "consumed_signal_ids",   # PM 消费去重指针
    "decision_log",          # PM 决策档案，支撑离线 Q&A
}


def test_ccastate_has_all_expected_fields() -> None:
    assert set(CCAState.__annotations__.keys()) == REQUIRED_FIELDS


def test_ccastate_has_task_plan_and_report_task() -> None:
    """阶段二/三 task 字段必须在 state 里；analyst_task 已并入 report_task。"""
    assert "task_plan" in CCAState.__annotations__
    assert "report_task" in CCAState.__annotations__
    assert "analyst_task" not in CCAState.__annotations__


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


# ── _merge_profiles：fanout 并发安全（空值不覆盖真数据）────────────────────

_FULL = {"瑞幸": {"product_name": "瑞幸",
                  "dimensions": [{"name": "门店"}], "sources": ["url1"]}}
# _skip_result 崩溃占位：带空 dimensions/sources，绝不能覆盖同 key 的 collector 真数据
_EMPTY_SHELL = {"瑞幸": {"product_name": "瑞幸", "company": None,
                        "dimensions": [], "sources": []}}


def test_merge_profiles_empty_list_never_clobbers_populated() -> None:
    """空 [] 不得覆盖已填 dimensions/sources —— 这条挂掉 = collector 真数据被空壳抹掉的 P0 回归。"""
    merged = _merge_profiles(_FULL, _EMPTY_SHELL)
    assert merged["瑞幸"]["dimensions"] == [{"name": "门店"}]
    assert merged["瑞幸"]["sources"] == ["url1"]


def test_merge_profiles_clobber_is_fold_order_independent() -> None:
    """无论 collector(full) 与崩溃 worker(shell) 谁先 fold，真数据都保留。"""
    full_then_shell = reduce(_merge_profiles, [_FULL, _EMPTY_SHELL], {})
    shell_then_full = reduce(_merge_profiles, [_EMPTY_SHELL, _FULL], {})
    assert full_then_shell == shell_then_full
    assert full_then_shell["瑞幸"]["dimensions"] == [{"name": "门店"}]


def test_merge_profiles_none_does_not_clobber() -> None:
    """保留原契约：右侧 None 不覆盖左侧已有值（防二轮清空 sentiment）。"""
    left = {"A": {"sentiment": {"score": 0.8}}}
    right = {"A": {"sentiment": None}}
    assert _merge_profiles(left, right)["A"]["sentiment"] == {"score": 0.8}


def test_merge_profiles_nonempty_overwrites() -> None:
    """非空 incoming 仍按"最新覆盖"，且 0/False 不被当空值丢弃。"""
    left = {"A": {"dimensions": [{"name": "旧"}], "flag": True, "n": 5}}
    right = {"A": {"dimensions": [{"name": "新"}], "flag": False, "n": 0}}
    out = _merge_profiles(left, right)["A"]
    assert out["dimensions"] == [{"name": "新"}]
    assert out["flag"] is False
    assert out["n"] == 0


def test_merge_profiles_cross_agent_fields_coexist() -> None:
    """collector(dimensions/sources) 与 insight(sentiment) 同 key 各写各的，互不丢。"""
    collector = {"A": {"product_name": "A", "dimensions": [{"name": "d"}], "sources": ["u"]}}
    insight = {"A": {"sentiment": {"score": 0.9}}}
    out = reduce(_merge_profiles, [collector, insight], {})["A"]
    assert out["dimensions"] == [{"name": "d"}]
    assert out["sentiment"] == {"score": 0.9}


def test_merge_profiles_disjoint_keys_both_kept() -> None:
    merged = _merge_profiles({"A": {"x": 1}}, {"B": {"y": 2}})
    assert merged == {"A": {"x": 1}, "B": {"y": 2}}
