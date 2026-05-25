"""PM Agent 测试（不调真 API）。

覆盖 4 个阶段节点的输出结构 + 信号处理，不测试 LLM 内容质量。
"""

from __future__ import annotations

import pytest

from cca.schema import (
    AgentSignal,
    AnalystTask,
    DebateResult,
    InitialBrief,
    ReportTask,
    TaskPlan,
)
from cca.state import CCAState


class _FakeStructuredLLM:
    """模拟 with_structured_output() 返回的可调用对象。"""

    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):
        return self._response


def _patch_pm_gpt(monkeypatch: pytest.MonkeyPatch, response):
    """替换 pm.gpt.with_structured_output 为 fake。"""
    fake = _FakeStructuredLLM(response)

    class _FakeGPT:
        def with_structured_output(self, target_type, method=None):  # noqa: ARG002
            return fake

    monkeypatch.setattr("cca.agents.pm.gpt", _FakeGPT(), raising=False)


def _make_minimal_state(**overrides) -> CCAState:
    state: CCAState = {
        "user_query": "分析飞书",
        "target_product": "飞书",
        "initial_brief": None,
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "analyst_task": None,
        "report_task": None,
        "profiles": {},
        "review_state": [],
        "qa_results": [],
        "report_status": "pending",
        "report_md": None,
        "report_pdf_path": None,
        "qa_notes": [],
        "audit_log": [],
        "debate_results": [],
        "agent_signals": [],
    }
    state.update(overrides)  # type: ignore[typeddict-unknown-key]
    return state


# ── Phase 1: InitialBrief ──────────────────────────────────────────────


def test_initial_brief_node_returns_initial_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    brief = InitialBrief(
        target_product="飞书",
        company_hint="字节跳动",
        user_query="分析飞书",
        rationale="用户明确指定飞书",
    )
    _patch_pm_gpt(monkeypatch, brief)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(_make_minimal_state(user_query="分析飞书"))
    assert "initial_brief" in result
    assert result["initial_brief"]["target_product"] == "飞书"
    assert result["initial_brief"]["company_hint"] == "字节跳动"


# ── Phase 2: TaskPlan ──────────────────────────────────────────────────


def test_task_plan_node_returns_task_plan_and_competitors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = TaskPlan(
        target_product="飞书",
        product_type="协作办公SaaS",
        competitor_names=["钉钉", "企业微信"],
        collect_tasks=[],
        insight_tasks=[],
        rationale="exploration 确认",
    )
    _patch_pm_gpt(monkeypatch, plan)

    from cca.agents.pm import task_plan_node

    state = _make_minimal_state(
        exploration_result={
            "target_product": "飞书",
            "product_type": "协作办公SaaS",
            "competitor_names": ["钉钉", "企业微信"],
            "discovered_dimensions": ["视频会议", "定价"],
            "initial_profiles": [],
        },
    )
    result = task_plan_node(state)
    assert "task_plan" in result
    assert result["task_plan"]["product_type"] == "协作办公SaaS"
    assert result["competitor_names"] == ["钉钉", "企业微信"]


# ── Phase 3: AnalystTask ───────────────────────────────────────────────


def test_analyst_task_node_returns_analyst_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = AnalystTask(
        product_names=["飞书", "钉钉", "企业微信"],
        focus_dimensions=["视频会议", "定价"],
        require_swot=True,
    )
    _patch_pm_gpt(monkeypatch, task)

    from cca.agents.pm import analyst_task_node

    state = _make_minimal_state(
        competitor_names=["钉钉", "企业微信"],
        profiles={
            "钉钉": {"product_name": "钉钉", "dimensions": []},
            "企业微信": {"product_name": "企业微信", "dimensions": []},
        },
    )
    result = analyst_task_node(state)
    assert "analyst_task" in result
    assert result["analyst_task"]["require_swot"] is True
    assert "飞书" in result["analyst_task"]["product_names"]


# ── Phase 4: ReportTask ────────────────────────────────────────────────


def test_report_task_node_returns_report_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = ReportTask(
        target_product="飞书",
        competitors=["钉钉", "企业微信"],
        output_formats=["markdown", "pdf"],
        target_audience="产品负责人",
        sections=["执行摘要", "SWOT 分析"],
        invoke_call_report_reviewer=True,
    )
    _patch_pm_gpt(monkeypatch, task)

    from cca.agents.pm import report_task_node

    state = _make_minimal_state(
        competitor_names=["钉钉", "企业微信"],
        profiles={
            "钉钉": {"product_name": "钉钉", "swot": {}},
            "企业微信": {"product_name": "企业微信", "swot": {}},
        },
    )
    result = report_task_node(state)
    assert "report_task" in result
    assert result["report_task"]["target_product"] == "飞书"
    assert result["report_task"]["invoke_call_report_reviewer"] is True


# ── Edge cases ─────────────────────────────────────────────────────────


def test_initial_brief_passes_user_query_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_query 原样透传，不做加工。"""
    brief = InitialBrief(
        target_product="小米 Buds 4",
        company_hint="小米",
        user_query="分析 200 元内的耳机",
        rationale="用户未指定具体产品，PM 选取代表",
    )
    _patch_pm_gpt(monkeypatch, brief)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(_make_minimal_state(user_query="分析 200 元内的耳机"))
    assert result["initial_brief"]["user_query"] == "分析 200 元内的耳机"


def test_prompt_file_loads() -> None:
    """系统 prompt 文件存在且非空。"""
    from cca.agents.pm import _load_system_prompt

    prompt = _load_system_prompt()
    assert len(prompt) > 200
    assert "InitialBrief" in prompt
    assert "TaskPlan" in prompt


# ── _read_defense ──────────────────────────────────────────────────────


def test_read_defense_task_plan() -> None:
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        task_plan={
            "rationale": "exploration 确认竞品列表",
            "product_type": "协作办公SaaS",
            "competitor_names": ["钉钉", "企业微信"],
        },
    )
    pos = _read_defense("task_plan", state)
    assert pos.agent_family == "gpt-5"
    assert "exploration 确认竞品列表" in pos.claim
    assert any("协作办公SaaS" in e for e in pos.evidence)
    assert any("钉钉" in e for e in pos.evidence)


def test_read_defense_analyst_task() -> None:
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        analyst_task={
            "focus_dimensions": ["视频会议", "定价"],
            "product_names": ["飞书", "钉钉"],
        },
    )
    pos = _read_defense("analyst_task", state)
    assert "视频会议" in pos.claim
    assert any("飞书" in e for e in pos.evidence)


def test_read_defense_report_task() -> None:
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        report_task={
            "sections": ["执行摘要", "SWOT 分析"],
            "target_audience": "产品负责人",
            "competitors": ["钉钉"],
        },
    )
    pos = _read_defense("report_task", state)
    assert "执行摘要" in pos.claim
    assert "产品负责人" in pos.claim
    assert any("钉钉" in e for e in pos.evidence)


def test_read_defense_unknown_target_falls_back() -> None:
    from cca.agents.pm import _read_defense

    state = _make_minimal_state()
    pos = _read_defense("unknown_key", state)
    assert pos.agent_family == "gpt-5"
    assert pos.claim == "PM 决策"
    assert pos.evidence == ["state context"]


# ── _apply_debate_result ───────────────────────────────────────────────


def _make_debate_result(**overrides) -> DebateResult:
    defaults: dict = {
        "target": "pm_taskplan",
        "rounds": [],
        "final_verdict": "accepted",
        "judge_family": None,
        "judge_rationale": "",
        "revised_output": None,
    }
    defaults.update(overrides)
    return DebateResult(**defaults)


def test_apply_debate_result_accepted_revises_task_plan() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="pm_taskplan",
        final_verdict="accepted_with_revision",
        revised_output={"product_type": "IM SaaS", "competitor_names": ["钉钉"]},
    )
    updates = _apply_debate_result(result)
    assert updates["task_plan"] == result.revised_output
    assert updates["competitor_names"] == ["钉钉"]
    assert updates["audit_log"][0]["verdict"] == "accepted_with_revision"


def test_apply_debate_result_rejected_only_logs() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="pm_taskplan",
        final_verdict="rejected",
        revised_output={"product_type": "IM SaaS"},
    )
    updates = _apply_debate_result(result)
    assert "task_plan" not in updates
    assert updates["audit_log"][0]["verdict"] == "rejected"


def test_apply_debate_result_analyst_target() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="analyst_swot",
        final_verdict="accepted_with_revision",
        revised_output={"focus_dimensions": ["定价"]},
    )
    updates = _apply_debate_result(result)
    assert updates["analyst_task"] == result.revised_output


def test_apply_debate_result_report_target() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="report",
        final_verdict="accepted_with_revision",
        revised_output={"sections": ["概述"]},
    )
    updates = _apply_debate_result(result)
    assert updates["report_task"] == result.revised_output


# ── handle_signal_node ─────────────────────────────────────────────────


def test_handle_signal_node_empty_returns_empty() -> None:
    from cca.agents.pm import handle_signal_node

    result = handle_signal_node(_make_minimal_state(agent_signals=[]))
    assert result == {}


def test_handle_signal_node_debate_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from cca.agents.pm import handle_signal_node

    debate_result = _make_debate_result(final_verdict="accepted_with_revision")
    monkeypatch.setattr(
        "cca.agents.pm.run_debate",
        lambda **kwargs: debate_result,  # noqa: ARG005
        raising=False,
    )

    signal = AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="task_plan",
        payload={"reason": "竞品列表不完整"},
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        task_plan={"rationale": "test", "product_type": "SaaS", "competitor_names": ["钉钉"]},
    )
    result = handle_signal_node(state)
    assert "debate_results" in result
    assert result["audit_log"][0]["event"] == "debate_applied"


def test_handle_signal_node_debate_from_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """challenge 从 signal.payload 构造 DebatePosition。"""
    from cca.agents.pm import handle_signal_node

    debate_result = _make_debate_result(final_verdict="accepted")
    monkeypatch.setattr("cca.agents.pm.run_debate", lambda **kwargs: debate_result, raising=False)

    signal = AgentSignal(
        from_agent="insight",
        kind="other",
        target="analyst_task",
        payload={"reason": "维度不足"},
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        analyst_task={"focus_dimensions": ["功能"], "product_names": ["飞书"]},
    )
    result = handle_signal_node(state)
    assert "debate_results" in result


def test_handle_signal_node_reroute_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from cca.agents.pm import handle_signal_node
    from cca.skills.reroute import RerouteDecision

    decision = RerouteDecision(
        target_phase="phase_1",
        root_cause="定价数据缺失",
        fix_summary={},
        rationale="采集层缺失数据",
    )
    monkeypatch.setattr("cca.agents.pm.reroute", lambda s, state_json: decision, raising=False)
    monkeypatch.setattr(
        "cca.agents.pm.apply_reroute",
        lambda d, s: {"exploration_result": None, "audit_log": [{"agent": "reroute"}]},
        raising=False,
    )

    signal = AgentSignal(
        from_agent="collector",
        kind="data_gap",
        target="collector:企业微信",
        payload={"reason": "定价数据缺失"},
        requires_debate=False,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(agent_signals=[signal.model_dump()])
    result = handle_signal_node(state)
    assert result["exploration_result"] is None
    assert result["audit_log"][0]["agent"] == "reroute"


def test_handle_signal_node_multiple_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    from cca.agents.pm import handle_signal_node
    from cca.skills.reroute import RerouteDecision

    debate_result = _make_debate_result(final_verdict="accepted")
    monkeypatch.setattr("cca.agents.pm.run_debate", lambda **kwargs: debate_result, raising=False)

    reroute_decision = RerouteDecision(
        target_phase="phase_2",
        root_cause="x",
        fix_summary={},
        rationale="y",
    )
    monkeypatch.setattr(
        "cca.agents.pm.reroute", lambda s, state_json: reroute_decision, raising=False
    )
    monkeypatch.setattr(
        "cca.agents.pm.apply_reroute",
        lambda d, s: {"task_plan": None, "audit_log": [{"agent": "reroute"}]},
        raising=False,
    )

    debate_signal = AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="task_plan",
        payload={},
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    reroute_signal = AgentSignal(
        from_agent="collector",
        kind="data_gap",
        target="collector:X",
        payload={},
        requires_debate=False,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[debate_signal.model_dump(), reroute_signal.model_dump()],
        task_plan={"rationale": "test"},
    )
    result = handle_signal_node(state)
    assert "debate_results" in result
    assert result["task_plan"] is None
    # reroute 先于 debate，audit_log 顺序应为 [reroute, debate_applied]
    assert [e.get("agent") for e in result["audit_log"]] == ["reroute", "pm"]


def test_handle_signal_node_multiple_debates_all_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个 debate 信号同时来时，两份 DebateResult 都要进 debate_results，不能互覆。"""
    from cca.agents.pm import handle_signal_node

    results_iter = iter(
        [
            _make_debate_result(final_verdict="accepted", judge_rationale="r1"),
            _make_debate_result(
                target="analyst_swot",
                final_verdict="accepted",
                judge_rationale="r2",
            ),
        ]
    )
    monkeypatch.setattr(
        "cca.agents.pm.run_debate", lambda **kwargs: next(results_iter), raising=False
    )

    sig1 = AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="task_plan",
        payload={"reason": "竞品列表不完整"},
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    sig2 = AgentSignal(
        from_agent="insight",
        kind="other",
        target="analyst_task",
        payload={"reason": "维度不足"},
        requires_debate=True,
        ts="2026-05-23T00:00:01Z",
    )
    state = _make_minimal_state(
        agent_signals=[sig1.model_dump(), sig2.model_dump()],
        task_plan={"rationale": "t", "product_type": "SaaS", "competitor_names": ["X"]},
        analyst_task={"focus_dimensions": ["d"], "product_names": ["P"]},
    )
    result = handle_signal_node(state)
    assert len(result["debate_results"]) == 2
    assert {r["judge_rationale"] for r in result["debate_results"]} == {"r1", "r2"}
    assert len(result["audit_log"]) == 2
