"""PM Agent tests (no real API calls).

Covers the output structure of the 3 phase nodes + signal handling; doesn't test LLM content quality.
"""

from __future__ import annotations

import pytest

from cca.schema import (
    AgentSignal,
    DebateResult,
    DecisionRecord,
    DomainSeed,
    InitialBrief,
    InitialBriefOutput,
    ReportTask,
    ReportTaskOutput,
    ReviewOutput,
    ReviewUnit,
    TaskPlan,
    TaskPlanOutput,
)
from cca.state import CCAState


def _mk_decision(decision_type: str = "other", **overrides) -> DecisionRecord:
    """Build a minimal usable DecisionRecord, embedded in fake LLM responses. phase gets overwritten by the node."""
    defaults: dict = {
        "phase": "initial_brief",
        "decision_type": decision_type,
        "chosen": {"k": "v"},
        "rationale": "test rationale",
    }
    defaults.update(overrides)
    return DecisionRecord(**defaults)


def _mk_payload(text: str) -> dict:
    """Build ChallengePayload's dict shape for AgentSignal.payload."""
    return {"claim": text, "evidence": [text]}


class _FakeStructuredLLM:
    """Simulates the callable returned by with_structured_output()."""

    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):
        return self._response


class _FakeMessage:
    """Simulates the AIMessage returned by a direct (non-structured) ChatOpenAI call."""

    def __init__(self, content: str):
        self.content = content


def _patch_pm_gpt(monkeypatch: pytest.MonkeyPatch, response, *, fallback_content: str = ""):
    """Replace pm.get_llm: with_structured_output goes through the fake; a direct invoke goes through the JSON fallback.

    fallback_content is the raw text returned by the fallback channel; empty by
    default -> pydantic validation fails -> _invoke_pm raises.
    """
    fake = _FakeStructuredLLM(response)

    class _FakeGPT:
        def with_structured_output(self, target_type, method=None):  # noqa: ARG002
            return fake

        def invoke(self, _messages):
            return _FakeMessage(fallback_content)

    monkeypatch.setattr("cca.agents.pm.get_llm", lambda _family: _FakeGPT())


def _make_minimal_state(**overrides) -> CCAState:
    state: CCAState = {
        "user_query": "分析飞书",
        "target_product": "飞书",
        "user_files": None,
        "initial_brief": None,
        "domain_seed": None,
        "exploration_result": None,
        "competitor_names": [],
        "task_plan": None,
        "report_task": None,
        "profiles": {},
        "review_state": [],
        "reroute_count": 0,
        "qa_results": [],
        "report_status": "pending",
        "report_md": None,
        "report_pdf_path": None,
        "qa_notes": [],
        "audit_log": [],
        "debate_results": [],
        "agent_signals": [],
        "consumed_signal_ids": [],
        "decision_log": [],
    }
    state.update(overrides)  # type: ignore[typeddict-unknown-key]
    return state


# ── Phase 1: InitialBrief ────────────────────────────────────────────


def test_initial_brief_node_returns_initial_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书",
            company_hint="字节跳动",
            user_query="分析飞书",
        ),
        decision_records=[_mk_decision("target_product_selection")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(_make_minimal_state(user_query="分析飞书"))
    assert "initial_brief" in result
    assert result["initial_brief"]["target_product"] == "飞书"
    assert result["initial_brief"]["company_hint"] == "字节跳动"
    assert len(result["decision_log"]) == 1
    assert result["decision_log"][0]["phase"] == "initial_brief"
    assert result["decision_log"][0]["decision_type"] == "target_product_selection"
    # no file uploaded -> domain_seed isn't in updates
    assert "domain_seed" not in result


def test_initial_brief_node_writes_back_refined_target_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PM's refined target_product is written back to state, becoming the single source of truth (overwriting the raw entry value)."""
    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="小米 Buds 4",
            company_hint="小米",
            user_query="分析 200 元内的耳机",
        ),
        decision_records=[_mk_decision("target_product_selection")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(
        _make_minimal_state(user_query="分析 200 元内的耳机", target_product="耳机")
    )
    assert result["target_product"] == "小米 Buds 4"


def test_initial_brief_node_consumes_user_file_and_produces_domain_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """state.user_files has a path -> text is extracted and fed into the prompt -> the
    LLM returns a DomainSeed -> it lands in state.domain_seed."""
    seed_file = tmp_path / "market.md"
    seed_file.write_text(
        "# 市场调研\n飞书在协同办公赛道，主要对手是钉钉、企业微信。\n关键维度：视频会议、AI 助手、定价。",
        encoding="utf-8",
    )

    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书",
            company_hint="字节跳动",
            user_query="分析飞书",
        ),
        decision_records=[_mk_decision("target_product_selection")],
        domain_seed=DomainSeed(
            source_files=[],  # LLM 留空，节点端覆盖
            dimension_candidates=["视频会议", "AI 助手", "定价"],
            competitor_mentions=["钉钉", "企业微信"],
            product_type_hint="协同办公平台",
        ),
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(
        _make_minimal_state(user_query="分析飞书", user_files=[str(seed_file)])
    )
    assert "domain_seed" in result
    ds = result["domain_seed"]
    assert ds["source_files"] == [str(seed_file)]  # 节点端强制覆盖
    assert ds["dimension_candidates"] == ["视频会议", "AI 助手", "定价"]
    assert ds["competitor_mentions"] == ["钉钉", "企业微信"]


def test_initial_brief_node_missing_user_file_logs_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File path doesn't exist -> no exception raised, audit_log records file_read_failed, no domain_seed."""
    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书", company_hint=None, user_query="分析飞书",
        ),
        decision_records=[_mk_decision("target_product_selection")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(
        _make_minimal_state(user_files=["/no/such/file.pdf"])
    )
    assert "domain_seed" not in result
    assert any(
        e.get("event") == "file_read_failed" for e in result.get("audit_log", [])
    )


def test_initial_brief_node_multi_file_keeps_first_logs_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """Multiple files -> only the first is read + audit_log records multi_file_warning."""
    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("first", encoding="utf-8")
    f2.write_text("second", encoding="utf-8")

    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书", company_hint=None, user_query="x",
        ),
        decision_records=[_mk_decision("target_product_selection")],
        domain_seed=DomainSeed(source_files=[], dimension_candidates=["d"]),
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(
        _make_minimal_state(user_files=[str(f1), str(f2)])
    )
    assert result["domain_seed"]["source_files"] == [str(f1)]
    assert any(
        e.get("event") == "multi_file_warning" for e in result.get("audit_log", [])
    )


def test_initial_brief_node_skips_domain_seed_when_llm_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """File was read but the LLM didn't return domain_seed -> state.domain_seed is not written."""
    p = tmp_path / "x.md"
    p.write_text("noise", encoding="utf-8")

    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="飞书", company_hint=None, user_query="x",
        ),
        decision_records=[_mk_decision("target_product_selection")],
        domain_seed=None,  # LLM 判断没有 hint 可提
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(_make_minimal_state(user_files=[str(p)]))
    assert "domain_seed" not in result


# ── Phase 2: TaskPlan ──────────────────────────────────────────────────


def test_task_plan_node_returns_task_plan_and_competitors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = TaskPlanOutput(
        task_plan=TaskPlan(
            target_product="飞书",
            product_type="协作办公SaaS",
            competitor_names=["钉钉", "企业微信"],
            collect_tasks=[],
            insight_tasks=[],
        ),
        decision_records=[
            _mk_decision("competitor_selection"),
            _mk_decision("dimension_priority"),
        ],
    )
    _patch_pm_gpt(monkeypatch, output)

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
    assert len(result["decision_log"]) == 2
    assert all(d["phase"] == "task_plan" for d in result["decision_log"])


def _mk_taskplan_output() -> TaskPlanOutput:
    return TaskPlanOutput(
        task_plan=TaskPlan(
            target_product="飞书",
            product_type="协作办公SaaS",
            competitor_names=["钉钉"],
            collect_tasks=[],
            insight_tasks=[],
        ),
        decision_records=[_mk_decision("task_allocation")],
    )


def test_invoke_pm_falls_back_to_json_when_structured_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """function_calling keeps returning None -> falls back to the raw JSON channel, parsed locally into a real object."""
    _patch_pm_gpt(monkeypatch, None, fallback_content=_mk_taskplan_output().model_dump_json())

    from cca.agents.pm import _invoke_pm

    result = _invoke_pm(TaskPlanOutput, "阶段二 TaskPlan", {"user_query": "x"})
    assert isinstance(result, TaskPlanOutput)
    assert result.task_plan.product_type == "协作办公SaaS"
    assert result.task_plan.competitor_names == ["钉钉"]


def test_invoke_pm_json_fallback_strips_markdown_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback channel: JSON can still be extracted even when the model wraps it in a ```json fence."""
    fenced = f"```json\n{_mk_taskplan_output().model_dump_json()}\n```"
    _patch_pm_gpt(monkeypatch, None, fallback_content=fenced)

    from cca.agents.pm import _invoke_pm

    result = _invoke_pm(TaskPlanOutput, "阶段二 TaskPlan", {"user_query": "x"})
    assert isinstance(result, TaskPlanOutput)


def test_invoke_pm_raises_when_structured_and_json_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither channel produces a valid structure -> RuntimeError, letting the caller decide whether to crash or degrade."""
    _patch_pm_gpt(monkeypatch, None, fallback_content="对不起，我无法完成。")

    from cca.agents.pm import _invoke_pm

    with pytest.raises(RuntimeError):
        _invoke_pm(TaskPlanOutput, "阶段二 TaskPlan", {"user_query": "x"})


# -- Phase 3: ReportTask (merges the former AnalystTask fields) --------------------


def test_report_task_node_returns_report_task(monkeypatch: pytest.MonkeyPatch) -> None:
    output = ReportTaskOutput(
        report_task=ReportTask(
            target_product="飞书",
            competitors=["钉钉", "企业微信"],
            product_names=["飞书", "钉钉", "企业微信"],
            focus_dimensions=["视频会议", "定价"],
            require_swot=True,
            cross_product_comparison_required=True,
            output_formats=["markdown", "pdf"],
            target_audience="产品负责人",
            sections=["执行摘要", "SWOT 分析"],
            invoke_call_report_reviewer=True,
        ),
        decision_records=[
            _mk_decision("analysis_focus"),
            _mk_decision("report_structure"),
            _mk_decision("audience_choice"),
        ],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import report_task_node

    state = _make_minimal_state(
        competitor_names=["钉钉", "企业微信"],
        profiles={
            "钉钉": {"product_name": "钉钉", "dimensions": []},
            "企业微信": {"product_name": "企业微信", "dimensions": []},
        },
    )
    result = report_task_node(state)
    assert "report_task" in result
    assert result["report_task"]["target_product"] == "飞书"
    assert result["report_task"]["require_swot"] is True
    assert "飞书" in result["report_task"]["product_names"]
    assert result["report_task"]["focus_dimensions"] == ["视频会议", "定价"]
    assert result["report_task"]["invoke_call_report_reviewer"] is True
    assert len(result["decision_log"]) == 3
    assert all(d["phase"] == "report_task" for d in result["decision_log"])


# ── Edge cases ─────────────────────────────────────────────────────────


def test_initial_brief_passes_user_query_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_query is passed through unchanged, no processing."""
    output = InitialBriefOutput(
        initial_brief=InitialBrief(
            target_product="小米 Buds 4",
            company_hint="小米",
            user_query="分析 200 元内的耳机",
        ),
        decision_records=[_mk_decision("target_product_selection")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import initial_brief_node

    result = initial_brief_node(_make_minimal_state(user_query="分析 200 元内的耳机"))
    assert result["initial_brief"]["user_query"] == "分析 200 元内的耳机"


def test_stamp_decisions_overrides_phase() -> None:
    """When the LLM misreports phase, _stamp_decisions must overwrite it with the phase specified by the node."""
    from cca.agents.pm import _stamp_decisions

    records = [
        DecisionRecord(
            phase="initial_brief",  # LLM 自报错
            decision_type="competitor_selection",
            chosen={"competitors": ["X"]},
            rationale="x",
        ),
    ]
    out = _stamp_decisions(records, "task_plan")
    assert out[0]["phase"] == "task_plan"


def test_prompt_file_loads() -> None:
    """The system prompt file exists and is non-empty."""
    from cca.agents.pm import _load_system_prompt

    prompt = _load_system_prompt()
    assert len(prompt) > 200
    assert "InitialBrief" in prompt
    assert "TaskPlan" in prompt


# ── _read_defense ──────────────────────────────────────────────────────


def _mk_decision_dict(
    phase: str,
    decision_type: str,
    rationale: str,
    chosen: dict | None = None,
    alternatives: list[dict] | None = None,
    inputs_used: list[str] | None = None,
) -> dict:
    """Builds a single decision_log record dict (already in model_dump form)."""
    return DecisionRecord(
        phase=phase,  # type: ignore[arg-type]
        decision_type=decision_type,
        rationale=rationale,
        chosen=chosen or {},
        alternatives_considered=alternatives or [],  # type: ignore[arg-type]
        inputs_used=inputs_used or [],
    ).model_dump()


def test_read_defense_task_plan_reads_decision_log() -> None:
    """defense is no longer assembled from the task_plan field; it's aggregated from decision_log entries of the same phase."""
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        decision_log=[
            _mk_decision_dict(
                phase="task_plan",
                decision_type="competitor_selection",
                rationale="exploration 确认头部市占率竞品",
                chosen={"competitors": ["钉钉", "企业微信"]},
                alternatives=[
                    {"option": "腾讯会议", "rejected_reason": "属视频会议工具，不对齐"}
                ],
                inputs_used=["exploration_result.competitor_names"],
            ),
        ],
    )
    pos = _read_defense("task_plan", state)
    assert pos.agent_family == "gpt-5"
    assert "exploration 确认头部市占率竞品" in pos.claim
    assert "[competitor_selection]" in pos.claim
    assert any("钉钉" in e for e in pos.evidence)
    assert any("腾讯会议" in e for e in pos.evidence)
    assert any("exploration_result.competitor_names" in e for e in pos.evidence)


def test_read_defense_report_task_reads_decision_log() -> None:
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        decision_log=[
            _mk_decision_dict(
                phase="report_task",
                decision_type="report_structure",
                rationale="按 SWOT 高亮项组织章节",
                chosen={"sections": ["执行摘要", "SWOT 分析"]},
            ),
            _mk_decision_dict(
                phase="report_task",
                decision_type="audience_choice",
                rationale="用户 query 表明面向产品负责人",
                chosen={"target_audience": "产品负责人"},
            ),
        ],
    )
    pos = _read_defense("report_task", state)
    # Both decisions land in claim
    assert "[report_structure]" in pos.claim
    assert "[audience_choice]" in pos.claim
    assert "按 SWOT 高亮项组织章节" in pos.claim
    assert "用户 query 表明面向产品负责人" in pos.claim


def test_read_defense_falls_back_when_no_decision() -> None:
    """When decision_log has no matching phase, a minimal placeholder defense is given instead of crashing."""
    from cca.agents.pm import _read_defense

    state = _make_minimal_state()
    pos = _read_defense("task_plan", state)
    assert pos.agent_family == "gpt-5"
    assert "decision_log 中无对应记录" in pos.claim
    assert pos.evidence == ["state context"]


def test_read_defense_ignores_decisions_from_other_phases() -> None:
    """The task_plan phase's defense should not mix in decisions from initial_brief / report_task."""
    from cca.agents.pm import _read_defense

    state = _make_minimal_state(
        decision_log=[
            _mk_decision_dict(
                phase="initial_brief",
                decision_type="target_product_selection",
                rationale="不应出现在 task_plan defense",
            ),
            _mk_decision_dict(
                phase="task_plan",
                decision_type="competitor_selection",
                rationale="应出现在 task_plan defense",
                chosen={"competitors": ["X"]},
            ),
        ],
    )
    pos = _read_defense("task_plan", state)
    assert "应出现在 task_plan defense" in pos.claim
    assert "不应出现在 task_plan defense" not in pos.claim


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


def test_apply_debate_result_rejected_clears_target_task() -> None:
    """A rejected verdict must clear the corresponding task field, triggering upstream routing to redo that phase."""
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="pm_taskplan",
        final_verdict="rejected",
        revised_output={"product_type": "IM SaaS"},  # not adopted even though the judge gave a revision
    )
    updates = _apply_debate_result(result)
    assert updates["task_plan"] is None
    assert updates["audit_log"][0]["verdict"] == "rejected"


def test_apply_debate_result_rejected_report_clears_report_task() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(target="report", final_verdict="rejected")
    updates = _apply_debate_result(result)
    assert updates["report_task"] is None


def test_apply_debate_result_report_target() -> None:
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="report",
        final_verdict="accepted_with_revision",
        revised_output={"sections": ["概述"]},
    )
    updates = _apply_debate_result(result)
    assert updates["report_task"] == result.revised_output


def test_apply_debate_result_initial_brief_revises_field() -> None:
    """pm_initial_brief's subjective challenge is accepted -> the revision is written back to the initial_brief field."""
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(
        target="pm_initial_brief",
        final_verdict="accepted_with_revision",
        revised_output={"target_product": "飞书", "company_hint": "字节跳动"},
    )
    updates = _apply_debate_result(result)
    assert updates["initial_brief"] == result.revised_output


def test_apply_debate_result_initial_brief_rejected_clears_field() -> None:
    """pm_initial_brief is rejected -> initial_brief is cleared, triggering routing back to redo phase 1."""
    from cca.agents.pm import _apply_debate_result

    result = _make_debate_result(target="pm_initial_brief", final_verdict="rejected")
    updates = _apply_debate_result(result)
    assert updates["initial_brief"] is None


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
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("竞品列表不完整"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        task_plan={"product_type": "SaaS", "competitor_names": ["钉钉"]},
    )
    result = handle_signal_node(state)
    assert "debate_results" in result
    assert result["audit_log"][0]["event"] == "debate_applied"


def test_handle_signal_node_debate_from_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The challenge builds a DebatePosition from signal.payload."""
    from cca.agents.pm import handle_signal_node

    debate_result = _make_debate_result(final_verdict="accepted")
    monkeypatch.setattr("cca.agents.pm.run_debate", lambda **kwargs: debate_result, raising=False)

    signal = AgentSignal(
        from_agent="insight",
        kind="other",
        target="report_task",
        payload=_mk_payload("维度不足"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        report_task={"target_product": "飞书", "competitors": ["钉钉"], "focus_dimensions": ["功能"]},
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
        lambda d: {"exploration_result": None, "audit_log": [{"agent": "reroute"}]},
        raising=False,
    )

    signal = AgentSignal(
        from_agent="collector",
        kind="data_gap",
        target="collector:企业微信",
        payload=_mk_payload("定价数据缺失"),
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
        lambda d: {"task_plan": None, "audit_log": [{"agent": "reroute"}]},
        raising=False,
    )

    debate_signal = AgentSignal(
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("挑战 task_plan"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    reroute_signal = AgentSignal(
        from_agent="collector",
        kind="data_gap",
        target="collector:X",
        payload=_mk_payload("数据缺口"),
        requires_debate=False,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[debate_signal.model_dump(), reroute_signal.model_dump()],
        task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert "debate_results" in result
    assert result["task_plan"] is None
    # reroute happens before debate, so audit_log order should be [reroute, debate_applied]
    assert [e.get("agent") for e in result["audit_log"]] == ["reroute", "pm"]


def test_handle_signal_node_multiple_debates_all_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When two debate signals arrive together, both DebateResults must land in debate_results without overwriting each other."""
    from cca.agents.pm import handle_signal_node

    results_iter = iter(
        [
            _make_debate_result(final_verdict="accepted", judge_rationale="r1"),
            _make_debate_result(
                target="report",
                final_verdict="accepted",
                judge_rationale="r2",
            ),
        ]
    )
    monkeypatch.setattr(
        "cca.agents.pm.run_debate", lambda **kwargs: next(results_iter), raising=False
    )

    sig1 = AgentSignal(
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("竞品列表不完整"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    sig2 = AgentSignal(
        from_agent="insight",
        kind="other",
        target="report_task",
        payload=_mk_payload("维度不足"),
        requires_debate=True,
        ts="2026-05-23T00:00:01Z",
    )
    state = _make_minimal_state(
        agent_signals=[sig1.model_dump(), sig2.model_dump()],
        task_plan={"product_type": "SaaS", "competitor_names": ["X"]},
        report_task={"target_product": "飞书", "competitors": ["P"], "focus_dimensions": ["d"]},
    )
    result = handle_signal_node(state)
    assert len(result["debate_results"]) == 2
    assert {r["judge_rationale"] for r in result["debate_results"]} == {"r1", "r2"}
    assert len(result["audit_log"]) == 2


def test_handle_signal_node_skips_already_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signal whose signal_id is already in consumed_signal_ids must be skipped, not re-triggering debate."""
    from cca.agents.pm import handle_signal_node

    called = {"count": 0}

    def _fake_run_debate(**_kwargs):  # noqa: ANN003
        called["count"] += 1
        return _make_debate_result(final_verdict="accepted")

    monkeypatch.setattr("cca.agents.pm.run_debate", _fake_run_debate, raising=False)

    signal = AgentSignal(
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("x"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        consumed_signal_ids=[signal.signal_id],
        task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert result == {}
    assert called["count"] == 0


def test_handle_signal_node_returns_consumed_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When processing a new signal, the signal_id consumed this round must appear in the returned consumed_signal_ids."""
    from cca.agents.pm import handle_signal_node

    monkeypatch.setattr(
        "cca.agents.pm.run_debate",
        lambda **kwargs: _make_debate_result(final_verdict="accepted"),  # noqa: ARG005
        raising=False,
    )

    signal = AgentSignal(
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("x"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert result["consumed_signal_ids"] == [signal.signal_id]


def test_handle_signal_node_initial_brief_debate_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """An initial_brief subjective challenge must map to debate target 'pm_initial_brief', not the default pm_taskplan."""
    from cca.agents.pm import handle_signal_node

    called: dict = {}

    def _fake_run_debate(**kwargs):  # noqa: ANN003
        called["target"] = kwargs["target"]
        return _make_debate_result(target="pm_initial_brief", final_verdict="accepted")

    monkeypatch.setattr("cca.agents.pm.run_debate", _fake_run_debate, raising=False)

    signal = AgentSignal(
        from_agent="collector",
        kind="pm_challenge",
        target="initial_brief",
        payload=_mk_payload("target_product 选得不合理"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()],
        initial_brief={"target_product": "飞书"},
    )
    result = handle_signal_node(state)
    assert called["target"] == "pm_initial_brief"
    assert result["consumed_signal_ids"] == [signal.signal_id]


def test_handle_signal_node_mixes_old_and_new(monkeypatch: pytest.MonkeyPatch) -> None:
    """When an old signal is already consumed and a new one isn't, only the new signal is processed."""
    from cca.agents.pm import handle_signal_node

    called_targets: list[str] = []

    def _fake_run_debate(**kwargs):  # noqa: ANN003
        called_targets.append(kwargs["target"])
        return _make_debate_result(final_verdict="accepted")

    monkeypatch.setattr("cca.agents.pm.run_debate", _fake_run_debate, raising=False)

    old = AgentSignal(
        from_agent="report",
        kind="pm_challenge",
        target="task_plan",
        payload=_mk_payload("old"),
        requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    new = AgentSignal(
        from_agent="insight",
        kind="other",
        target="report_task",
        payload=_mk_payload("new"),
        requires_debate=True,
        ts="2026-05-23T00:00:01Z",
    )
    state = _make_minimal_state(
        agent_signals=[old.model_dump(), new.model_dump()],
        consumed_signal_ids=[old.signal_id],
        task_plan={"product_type": "S"},
        report_task={"target_product": "飞书", "competitors": ["P"], "focus_dimensions": ["d"]},
    )
    result = handle_signal_node(state)
    # _TARGET_TO_DEBATE maps signal.target='report_task' to debate target='report'
    assert called_targets == ["report"]
    assert result["consumed_signal_ids"] == [new.signal_id]


# -- review_node + reroute_count upper limit --------------------------


def _mk_task_plan(*products: str) -> dict:
    """Builds a minimal task_plan: each product maps to one CollectTask + InsightTask."""
    return TaskPlan(
        target_product=products[0] if products else "x",
        product_type="SaaS",
        competitor_names=list(products[1:]),
        collect_tasks=[{"product_name": p} for p in products],  # type: ignore[arg-type]
        insight_tasks=[{"product_name": p} for p in products],  # type: ignore[arg-type]
    ).model_dump()


def _complete_profile(name: str) -> dict:
    """Builds a complete-data profile: 1 dim+fact, sources present, sentiment with >=3 reviews."""
    return {
        "product_name": name,
        "dimensions": [{
            "name": "视频会议",
            "category": "功能",
            "facts": [{
                "statement": f"{name} 支持 300 人会议",
                "evidence": [{"source_url": f"https://{name}.com", "snippet": "x",
                              "fetched_at": "2026-05-23T00:00:00Z"}],
            }],
        }],
        "sources": [{"source_url": f"https://{name}.com", "snippet": "x",
                     "fetched_at": "2026-05-23T00:00:00Z"}],
        "sentiment": {
            "representative_reviews": [
                {"text": "r1", "platform": "appstore_cn"},
                {"text": "r2", "platform": "appstore_cn"},
                {"text": "r3", "platform": "appstore_cn"},
            ],
        },
    }


def test_check_data_completeness_complete_profile_returns_empty() -> None:
    from cca.agents.pm import _check_data_completeness

    profiles = {"飞书": _complete_profile("飞书")}
    task_plan = _mk_task_plan("飞书")
    flags = _check_data_completeness(profiles, task_plan)
    assert flags == {}


def test_check_data_completeness_missing_dimensions_flags_collector() -> None:
    from cca.agents.pm import _check_data_completeness

    profiles = {"x": {"product_name": "x"}}  # no dimensions / sources / sentiment
    task_plan = _mk_task_plan("x")
    flags = _check_data_completeness(profiles, task_plan)
    assert "collector:x" in flags
    assert any("dimensions" in f for f in flags["collector:x"])
    assert any("sources" in f for f in flags["collector:x"])
    assert "insight:x" in flags
    assert any("sentiment" in f for f in flags["insight:x"])


def test_check_data_completeness_dim_without_facts_flagged() -> None:
    from cca.agents.pm import _check_data_completeness

    profiles = {"y": {
        "product_name": "y",
        "dimensions": [{"name": "定价", "category": "定价", "facts": []}],
        "sources": [{"source_url": "u", "snippet": "s", "fetched_at": "t"}],
        "sentiment": {"representative_reviews": [{"text": "r"}, {"text": "r"}, {"text": "r"}]},
    }}
    task_plan = _mk_task_plan("y")
    flags = _check_data_completeness(profiles, task_plan)
    assert "collector:y" in flags
    assert any("定价" in f for f in flags["collector:y"])


def test_check_data_completeness_sentiment_too_few_flagged() -> None:
    from cca.agents.pm import _check_data_completeness

    profiles = {"z": {
        "product_name": "z",
        "dimensions": [{"name": "x", "category": "x", "facts": [
            {"statement": "s", "evidence": [
                {"source_url": "u", "snippet": "s", "fetched_at": "t"}]},
        ]}],
        "sources": [{"source_url": "u", "snippet": "s", "fetched_at": "t"}],
        "sentiment": {"representative_reviews": []},  # 0 entries, below the floor
    }}
    task_plan = _mk_task_plan("z")
    flags = _check_data_completeness(profiles, task_plan)
    assert "insight:z" in flags
    assert any("sentiment_too_few" in f for f in flags["insight:z"])
    # Collector side has complete data, should have no flag
    assert "collector:z" not in flags


def _mk_review_output(*units: dict) -> ReviewOutput:
    """Builds a ReviewOutput; units look like {"agent":..., "product_name":..., "status":..., "retry_count":..., "qa_flags":[...]}."""
    return ReviewOutput(
        review_units=[ReviewUnit(**u) for u in units],
        decision_records=[_mk_decision("review_judgement")],
    )


def test_review_node_all_passed_no_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """All data complete + LLM marks passed -> review_state is all passed, no signal."""
    output = _mk_review_output(
        {"agent": "collector", "product_name": "飞书", "status": "passed", "retry_count": 0},
        {"agent": "insight", "product_name": "飞书", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"飞书": _complete_profile("飞书")},
        task_plan=_mk_task_plan("飞书"),
    )
    result = review_node(state)
    assert all(u["status"] == "passed" for u in result["review_state"])
    assert result["agent_signals"] == []
    assert result["audit_log"][0]["passed"] == 2
    assert result["audit_log"][0]["signals_raised"] == 0


def test_review_node_degrades_to_code_layer_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doubao repeatedly returns None -> _invoke_pm raises -> review doesn't crash, degrades to pure code-layer judgment.

    Complete-data products are still passed, missing-data products are still needs_retry -- code-layer pre_flags provide an independent fallback.
    """
    _patch_pm_gpt(monkeypatch, None)  # LLM always returns None -> the internal raise in review is caught

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"全": _complete_profile("全"), "缺": {"product_name": "缺"}},
        task_plan=_mk_task_plan("全", "缺"),
    )
    result = review_node(state)  # 不应抛
    assert result["audit_log"][0]["llm_degraded"] is True
    by_product = {(u["agent"], u["product_name"]): u["status"] for u in result["review_state"]}
    assert by_product[("collector", "全")] == "passed"
    assert by_product[("collector", "缺")] == "needs_retry"
    assert any(s["from_agent"] == "collector" for s in result["agent_signals"])


def test_review_node_B_constraint_coerces_llm_passed_when_pre_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan B hard constraint: when the code-layer pre_flag is non-empty, an LLM 'passed' label is overridden to needs_retry."""
    output = _mk_review_output(
        # LLM tries to "let it pass leniently", but the data is missing
        {"agent": "collector", "product_name": "x", "status": "passed", "retry_count": 0, "qa_flags": []},
        {"agent": "insight", "product_name": "x", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"x": {"product_name": "x"}},  # 数据全空
        task_plan=_mk_task_plan("x"),
    )
    result = review_node(state)
    collector_unit = next(u for u in result["review_state"] if u["agent"] == "collector")
    assert collector_unit["status"] == "needs_retry"
    assert any("dimensions" in f for f in collector_unit["qa_flags"])
    assert any(s["from_agent"] == "collector" for s in result["agent_signals"])


def test_review_node_reroute_count_at_limit_coerces_to_forced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reroute_count hits the limit -> all needs_retry are escalated to forced, no longer raising a signal."""
    output = _mk_review_output(
        {"agent": "collector", "product_name": "x", "status": "needs_retry", "retry_count": 0,
         "qa_flags": ["data_missing: x"]},
        {"agent": "insight", "product_name": "x", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import _REROUTE_HARD_LIMIT, review_node

    state = _make_minimal_state(
        profiles={"x": {"product_name": "x"}},
        task_plan=_mk_task_plan("x"),
        reroute_count=_REROUTE_HARD_LIMIT,
    )
    result = review_node(state)
    collector_unit = next(u for u in result["review_state"] if u["agent"] == "collector")
    assert collector_unit["status"] == "forced"
    assert result["agent_signals"] == []
    assert result["audit_log"][0]["forced"] >= 1


def test_review_node_per_unit_retry_limit_forces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single unit's historical retry_count hits the limit -> forced, no longer needs_retry.

    The profile gives insight side complete data to avoid interfering with the assertion; only collector side lacks data.
    """
    output = _mk_review_output(
        {"agent": "collector", "product_name": "x", "status": "needs_retry", "retry_count": 99,
         "qa_flags": ["data_missing: dim"]},
        {"agent": "insight", "product_name": "x", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import _PER_UNIT_RETRY_LIMIT, review_node

    # collector side has no dim/sources; insight side has complete sentiment -> only collector triggers pre_flag
    profile = _complete_profile("x")
    profile["dimensions"] = []
    profile["sources"] = []

    # historical review_state contains _PER_UNIT_RETRY_LIMIT needs_retry records for this collector
    historical = [
        ReviewUnit(agent="collector", product_name="x", status="needs_retry",
                   retry_count=i, qa_flags=["x"]).model_dump()
        for i in range(_PER_UNIT_RETRY_LIMIT)
    ]
    state = _make_minimal_state(
        profiles={"x": profile},
        task_plan=_mk_task_plan("x"),
        review_state=historical,
        reroute_count=0,
    )
    result = review_node(state)
    collector_unit = next(u for u in result["review_state"] if u["agent"] == "collector")
    assert collector_unit["status"] == "forced"
    assert collector_unit["retry_count"] == _PER_UNIT_RETRY_LIMIT
    # insight is complete -> passed, so agent_signals should be empty (collector is already forced, no raise)
    assert result["agent_signals"] == []


def test_review_node_llm_skips_unit_code_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM misses reviewing an (agent, product) -> code layer falls back to produce a ReviewUnit."""
    # LLM only returns one collector entry, missing insight
    output = ReviewOutput(
        review_units=[ReviewUnit(
            agent="collector", product_name="x", status="passed", retry_count=0,
        )],
        decision_records=[_mk_decision("review_judgement")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"x": _complete_profile("x")},
        task_plan=_mk_task_plan("x"),
    )
    result = review_node(state)
    assert len(result["review_state"]) == 2
    insight_unit = next(u for u in result["review_state"] if u["agent"] == "insight")
    assert insight_unit["pm_note"] == "LLM 漏审，代码层兜底"
    assert insight_unit["status"] == "passed"   # fallback scenario + no pre_flag -> passed


def test_handle_signal_node_bumps_reroute_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successfully rerouting a factual signal -> reroute_count += 1."""
    from cca.agents.pm import handle_signal_node
    from cca.skills.reroute import RerouteDecision

    decision = RerouteDecision(
        target_phase="phase_2", root_cause="x", fix_summary={}, rationale="y",
    )
    monkeypatch.setattr("cca.agents.pm.reroute", lambda s, ctx: decision, raising=False)
    monkeypatch.setattr(
        "cca.agents.pm.apply_reroute",
        lambda d: {"task_plan": None, "audit_log": [{"agent": "reroute"}]},
        raising=False,
    )
    signal = AgentSignal(
        from_agent="collector", kind="data_gap", target="task_plan",
        payload=_mk_payload("缺数据"), requires_debate=False,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(agent_signals=[signal.model_dump()], reroute_count=0)
    result = handle_signal_node(state)
    assert result["reroute_count"] == 1


def test_handle_signal_node_debate_only_does_not_bump_reroute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signal that only goes through debate should not increase reroute_count."""
    from cca.agents.pm import handle_signal_node

    monkeypatch.setattr(
        "cca.agents.pm.run_debate",
        lambda **kwargs: _make_debate_result(final_verdict="accepted"),
        raising=False,
    )
    signal = AgentSignal(
        from_agent="report", kind="pm_challenge", target="task_plan",
        payload=_mk_payload("x"), requires_debate=True,
        ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()], reroute_count=0,
        task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert "reroute_count" not in result   # not written back when there's no increment


def test_handle_signal_node_reroute_phase_skips_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """signal.reroute_phase is non-empty (review pre-check data_gap) -> task_plan is cleared directly, without calling the reroute LLM."""
    from cca.agents.pm import handle_signal_node

    def _boom(*_args, **_kwargs):
        raise AssertionError("reroute LLM should not be called")

    monkeypatch.setattr("cca.agents.pm.reroute", _boom, raising=False)
    signal = AgentSignal(
        from_agent="collector", kind="data_gap", target="task_plan",
        payload=_mk_payload("collector:x 数据评审失败"), requires_debate=False,
        reroute_phase="phase_2", ts="2026-05-23T00:00:00Z",
    )
    state = _make_minimal_state(
        agent_signals=[signal.model_dump()], reroute_count=0,
        task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert result["task_plan"] is None        # phase_2 field is cleared
    assert result["reroute_count"] == 1


def test_handle_signal_node_multiple_retry_signals_bump_reroute_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple needs_retry signals in the same round only bump reroute_count once (circuit breaker counts per round, not per signal)."""
    from cca.agents.pm import handle_signal_node

    monkeypatch.setattr("cca.agents.pm.reroute", lambda *a, **k: None, raising=False)
    sigs = [
        AgentSignal(
            from_agent="collector", kind="data_gap", target="task_plan",
            payload=_mk_payload(f"collector:{p} 失败"), requires_debate=False,
            reroute_phase="phase_2", ts="2026-05-23T00:00:00Z",
        ).model_dump()
        for p in ("x", "y", "z")
    ]
    state = _make_minimal_state(
        agent_signals=sigs, reroute_count=0, task_plan={"product_type": "S"},
    )
    result = handle_signal_node(state)
    assert result["reroute_count"] == 1        # still only +1 even with 3 signals


# ── Reporter dimension_canonical_map ─────────────────────────────────


class TestEnsureMappingCoverage:
    """_ensure_mapping_coverage is the Phase 2 post-hoc correction function."""

    def test_full_coverage_passes_through(self):
        from cca.agents.pm import _ensure_mapping_coverage
        report_task = ReportTask(
            target_product="t", competitors=["c"], product_names=["t", "c"],
            dimension_canonical_map={"dim_a": "X", "dim_b": "Y"},
        )
        profiles = {
            "t": {"dimensions": [{"name": "dim_a"}]},
            "c": {"dimensions": [{"name": "dim_b"}]},
        }
        coerced, fallback = _ensure_mapping_coverage(report_task, profiles)
        assert fallback == []
        assert coerced.dimension_canonical_map == {"dim_a": "X", "dim_b": "Y"}

    def test_missing_dim_falls_back_to_other(self):
        """LLM misses dim_b -> automatically falls into the '其他' bucket + returns a fallback list."""
        from cca.agents.pm import _FALLBACK_BUCKET, _ensure_mapping_coverage
        report_task = ReportTask(
            target_product="t", competitors=["c"], product_names=["t", "c"],
            dimension_canonical_map={"dim_a": "X"},   # missing dim_b
        )
        profiles = {
            "t": {"dimensions": [{"name": "dim_a"}]},
            "c": {"dimensions": [{"name": "dim_b"}]},
        }
        coerced, fallback = _ensure_mapping_coverage(report_task, profiles)
        assert fallback == ["dim_b"]
        assert coerced.dimension_canonical_map == {"dim_a": "X", "dim_b": _FALLBACK_BUCKET}


def test_report_task_node_logs_mapping_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """report_task_node misses a mapping -> audit_log records the fallback dim list."""
    output = ReportTaskOutput(
        report_task=ReportTask(
            target_product="飞书",
            competitors=["钉钉"],
            product_names=["飞书", "钉钉"],
            focus_dimensions=[],
            invoke_call_report_reviewer=False,
            dimension_canonical_map={"dim_a": "X"},   # missing dim_b
        ),
        decision_records=[_mk_decision("analysis_focus")],
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import report_task_node
    state = _make_minimal_state(
        competitor_names=["钉钉"],
        profiles={
            "飞书": {"product_name": "飞书", "dimensions": [{"name": "dim_a"}]},
            "钉钉": {"product_name": "钉钉", "dimensions": [{"name": "dim_b"}]},
        },
    )
    result = report_task_node(state)
    assert result["report_task"]["dimension_canonical_map"]["dim_b"] == "其他"
    assert any(
        e.get("event") == "mapping_fallback_others" and "dim_b" in e.get("fallback_dims", [])
        for e in result.get("audit_log", [])
    )


# -- Phase 2.5 human_gate + user feedback ---------------------------


def test_parse_feedback_variants() -> None:
    """interrupt resume value tolerance: str -> raw text, dict -> validated, empty -> approved."""
    from cca.agents.pm import _parse_feedback

    assert _parse_feedback("钉钉数据不全").raw_feedback == "钉钉数据不全"
    assert _parse_feedback("钉钉数据不全").has_revisions() is True
    assert _parse_feedback({"raw_feedback": "x"}).raw_feedback == "x"
    assert _parse_feedback("").approved is True
    assert _parse_feedback(None).approved is True
    assert _parse_feedback("").has_revisions() is False


def test_human_feedback_text_only_when_revisions() -> None:
    """_human_feedback_text: returns raw text when there are substantive revisions, returns None for approved / empty."""
    from cca.agents.pm import _human_feedback_text

    s1 = _make_minimal_state(human_review_feedback={"raw_feedback": "补采定价", "approved": False})
    assert _human_feedback_text(s1) == "补采定价"
    s2 = _make_minimal_state(human_review_feedback={"raw_feedback": None, "approved": True})
    assert _human_feedback_text(s2) is None
    s3 = _make_minimal_state(human_review_feedback=None)
    assert _human_feedback_text(s3) is None


def test_profiles_digest_lists_dimensions_and_platforms() -> None:
    """digest for the frontend table: dimension names / review count / scraped platforms."""
    from cca.agents.pm import _profiles_digest

    profiles = {
        "钉钉": {
            "dimensions": [{"name": "视频会议"}, {"name": "定价"}],
            "pricing": {"has_free_tier": True},
            "sentiment": {"representative_reviews": [
                {"text": "a", "platform": "appstore_cn"},
                {"text": "b", "platform": "zhihu"},
            ]},
        },
    }
    digest = _profiles_digest(profiles)
    assert len(digest) == 1
    row = digest[0]
    assert row["product_name"] == "钉钉"
    assert row["dimensions"] == ["视频会议", "定价"]
    assert row["review_count"] == 2
    assert row["platforms"] == ["appstore_cn", "zhihu"]
    assert row["has_pricing"] is True


def test_human_gate_skips_when_done() -> None:
    """human_review_done=True -> passes through directly, no interrupt (once-only guarantee)."""
    from cca.agents.pm import human_gate_node

    state = _make_minimal_state(human_review_done=True)
    assert human_gate_node(state) == {}


def test_human_gate_non_interactive_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """CCA_HUMAN_REVIEW disabled -> no pause, just sets done=True and passes through."""
    monkeypatch.delenv("CCA_HUMAN_REVIEW", raising=False)
    from cca.agents.pm import human_gate_node

    result = human_gate_node(_make_minimal_state())
    assert result == {"human_review_done": True}


def test_human_gate_interactive_collects_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """CCA_HUMAN_REVIEW enabled -> interrupt collects input; resumed text lands in feedback, consumed=False."""
    monkeypatch.setenv("CCA_HUMAN_REVIEW", "1")
    monkeypatch.setattr("cca.agents.pm.interrupt", lambda _payload: "钉钉定价没采全")

    from cca.agents.pm import human_gate_node

    result = human_gate_node(_make_minimal_state(profiles={"钉钉": {"dimensions": []}}))
    assert result["human_review_done"] is True
    assert result["human_feedback_consumed"] is False
    assert result["human_review_feedback"]["raw_feedback"] == "钉钉定价没采全"


def test_review_node_consumes_unconsumed_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unconsumed feedback exists -> review adopts it and marks consumed=True, audit records used_human_feedback."""
    output = _mk_review_output(
        {"agent": "collector", "product_name": "飞书", "status": "passed", "retry_count": 0},
        {"agent": "insight", "product_name": "飞书", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"飞书": _complete_profile("飞书")},
        task_plan=_mk_task_plan("飞书"),
        human_review_feedback={"raw_feedback": "飞书定价要补充", "approved": False},
        human_feedback_consumed=False,
    )
    result = review_node(state)
    assert result["human_feedback_consumed"] is True
    assert result["audit_log"][0]["used_human_feedback"] is True


def test_review_node_ignores_already_consumed_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """feedback already consumed -> review no longer adopts it, doesn't reset consumed, audit used_human_feedback=False."""
    output = _mk_review_output(
        {"agent": "collector", "product_name": "飞书", "status": "passed", "retry_count": 0},
        {"agent": "insight", "product_name": "飞书", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"飞书": _complete_profile("飞书")},
        task_plan=_mk_task_plan("飞书"),
        human_review_feedback={"raw_feedback": "飞书定价要补充", "approved": False},
        human_feedback_consumed=True,
    )
    result = review_node(state)
    assert "human_feedback_consumed" not in result
    assert result["audit_log"][0]["used_human_feedback"] is False


def test_review_node_ignores_approved_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """approved (no substantive revision) feedback -> review does not adopt it."""
    output = _mk_review_output(
        {"agent": "collector", "product_name": "飞书", "status": "passed", "retry_count": 0},
        {"agent": "insight", "product_name": "飞书", "status": "passed", "retry_count": 0},
    )
    _patch_pm_gpt(monkeypatch, output)

    from cca.agents.pm import review_node

    state = _make_minimal_state(
        profiles={"飞书": _complete_profile("飞书")},
        task_plan=_mk_task_plan("飞书"),
        human_review_feedback={"raw_feedback": None, "approved": True},
        human_feedback_consumed=False,
    )
    result = review_node(state)
    assert "human_feedback_consumed" not in result
    assert result["audit_log"][0]["used_human_feedback"] is False


def _capture_invoke_payload(monkeypatch: pytest.MonkeyPatch, captured: dict, response) -> None:
    """Monkeypatches _invoke_pm to capture the incoming payload and return the given structured response."""
    def _fake(output_type, label, payload, **_kw):  # noqa: ANN001, ARG001
        captured["payload"] = payload
        return response
    monkeypatch.setattr("cca.agents.pm._invoke_pm", _fake)


def test_task_plan_node_injects_human_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """feedback has a substantive revision -> the raw text is injected into task_plan payload for PM to rearrange sections."""
    captured: dict = {}
    response = TaskPlanOutput(
        task_plan=TaskPlan(
            target_product="飞书", product_type="SaaS",
            competitor_names=["钉钉"], collect_tasks=[], insight_tasks=[],
        ),
        decision_records=[_mk_decision("human_revision")],
    )
    _capture_invoke_payload(monkeypatch, captured, response)

    from cca.agents.pm import task_plan_node

    state = _make_minimal_state(
        exploration_result={"competitor_names": ["钉钉"]},
        human_review_feedback={"raw_feedback": "再加上腾讯会议", "approved": False},
    )
    task_plan_node(state)
    assert captured["payload"]["human_review_feedback"] == "再加上腾讯会议"


def test_task_plan_node_omits_feedback_key_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """No feedback -> payload doesn't contain the human_review_feedback key (backward compatible)."""
    captured: dict = {}
    response = TaskPlanOutput(
        task_plan=TaskPlan(
            target_product="飞书", product_type="SaaS",
            competitor_names=["钉钉"], collect_tasks=[], insight_tasks=[],
        ),
        decision_records=[_mk_decision("competitor_selection")],
    )
    _capture_invoke_payload(monkeypatch, captured, response)

    from cca.agents.pm import task_plan_node

    task_plan_node(_make_minimal_state(exploration_result={"competitor_names": ["钉钉"]}))
    assert "human_review_feedback" not in captured["payload"]


def test_build_reroute_context_excludes_large_fields() -> None:
    """The reroute context only includes decision-necessary slices, no profiles / audit_log / decision_log."""
    import json as _json

    from cca.agents.pm import _build_reroute_context

    state = _make_minimal_state(
        exploration_result={"product_type": "X"},
        task_plan={"product_type": "Y"},
        profiles={"飞书": {"product_name": "飞书", "dimensions": list(range(1000))}},
        audit_log=[{"big": "audit"}],
        decision_log=[{"big": "decision"}],
        debate_results=[{"big": "debate"}],
    )
    ctx_json = _build_reroute_context(state)
    parsed = _json.loads(ctx_json)
    assert "exploration_result" in parsed
    assert "task_plan" in parsed
    assert "profiles" not in parsed
    assert "audit_log" not in parsed
    assert "decision_log" not in parsed
    assert "debate_results" not in parsed
