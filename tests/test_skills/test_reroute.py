"""测试 reroute skill 流程（不调真 API）。"""

from __future__ import annotations

import pytest

from cca.schema import AgentSignal


class _FakeStructuredLLM:
    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):
        return self._response


def _patch_reroute_gpt(monkeypatch: pytest.MonkeyPatch, response):
    fake = _FakeStructuredLLM(response)

    class _FakeGPT:
        def with_structured_output(self, target_type):  # noqa: ARG002
            return fake

    monkeypatch.setattr("cca.skills.reroute.gpt", _FakeGPT(), raising=False)


def _mk_payload(text: str, **extra) -> dict:
    """ChallengePayload dict 形态。"""
    return {"claim": text, "evidence": [text], **extra}


def _make_signal(**overrides) -> AgentSignal:
    defaults = {
        "from_agent": "collector",
        "kind": "data_gap",
        "target": "collector:企业微信",
        "payload": _mk_payload("定价数据缺失"),
        "requires_debate": False,
        "ts": "2026-05-23T00:00:00Z",
    }
    defaults.update(overrides)
    return AgentSignal(**defaults)


def test_reroute_data_gap_returns_phase_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cca.skills.reroute import RerouteDecision, reroute

    decision = RerouteDecision(
        target_phase="phase_1",
        root_cause="Collector 采集遗漏定价信息",
        fix_summary={"product_name": "企业微信", "priority_dimensions": ["定价"]},
        rationale="缺失数据属于采集层，回溯到阶段 1 重采",
    )
    _patch_reroute_gpt(monkeypatch, decision)

    result = reroute(_make_signal(), '{"competitor_names": ["钉钉","企业微信"]}')
    assert result.target_phase == "phase_1"
    assert "定价" in result.root_cause


def test_reroute_stale_competitor_returns_phase_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cca.skills.reroute import RerouteDecision, reroute

    signal = _make_signal(
        from_agent="analyst",
        payload=_mk_payload("竞品 X 已停服 6 个月"),
    )
    decision = RerouteDecision(
        target_phase="phase_1",
        root_cause="竞品 X 已确认停服，采集数据无效",
        fix_summary={"remove_competitor": "X", "strategy": "Collector 重新探索替代竞品"},
        rationale="采集数据失效，需回到阶段 1 重新探索",
    )
    _patch_reroute_gpt(monkeypatch, decision)

    result = reroute(signal, '{"competitor_names": ["钉钉","企业微信","X"]}')
    assert result.target_phase == "phase_1"
    assert "停服" in result.root_cause


def test_reroute_unavailable_dimension_returns_phase_3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cca.skills.reroute import RerouteDecision, reroute

    signal = _make_signal(
        from_agent="analyst",
        kind="pm_challenge",
        payload=_mk_payload("指定的 focus_dimensions 中 'AI 助手' 数据不足"),
    )
    decision = RerouteDecision(
        target_phase="phase_3",
        root_cause="AnalystTask 指定维度数据不完整",
        fix_summary={"remove_dimensions": ["AI 助手"], "add_dimensions": ["视频会议"]},
        rationale="只需调整 focus_dimensions，不需要改竞品列表",
    )
    _patch_reroute_gpt(monkeypatch, decision)

    result = reroute(signal, '{"analyst_task": {"focus_dimensions": ["AI 助手"]}}')
    assert result.target_phase == "phase_3"


def test_reroute_low_confidence_forces_phase_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cca.skills.reroute import RerouteDecision, reroute

    signal = _make_signal(
        from_agent="collector",
        payload=_mk_payload(
            "多家竞品的定价和用户口碑数据大面积缺失",
            observed_data={"data_confidence": 0.2},
        ),
    )
    decision = RerouteDecision(
        target_phase="phase_1",
        root_cause="数据置信度极低，大面积不可用",
        fix_summary={"strategy": "全量重采"},
        rationale="置信度 < 0.3 强制回溯到阶段 1",
    )
    _patch_reroute_gpt(monkeypatch, decision)

    result = reroute(signal, '{"exploration_result": {"data_confidence": 0.2}}')
    assert result.target_phase == "phase_1"


def test_apply_reroute_phase_1_clears_exploration() -> None:
    from cca.skills.reroute import RerouteDecision, apply_reroute

    decision = RerouteDecision(
        target_phase="phase_1",
        root_cause="采集数据过期",
        fix_summary={},
        rationale="重新探索",
    )
    result = apply_reroute(decision)
    assert result["exploration_result"] is None


def test_apply_reroute_phase_2_clears_task_plan() -> None:
    from cca.skills.reroute import RerouteDecision, apply_reroute

    decision = RerouteDecision(
        target_phase="phase_2",
        root_cause="竞品列表需修正",
        fix_summary={"competitor_names": ["钉钉"]},
        rationale="修正后重新生成 TaskPlan",
    )
    result = apply_reroute(decision)
    assert result["task_plan"] is None


def test_apply_reroute_phase_3_clears_analyst_task() -> None:
    from cca.skills.reroute import RerouteDecision, apply_reroute

    decision = RerouteDecision(
        target_phase="phase_3",
        root_cause="维度需调整",
        fix_summary={},
        rationale="修正 AnalystTask",
    )
    result = apply_reroute(decision)
    assert result["analyst_task"] is None


def test_apply_reroute_logs_audit() -> None:
    from cca.skills.reroute import RerouteDecision, apply_reroute

    decision = RerouteDecision(
        target_phase="phase_2",
        root_cause="x",
        fix_summary={},
        rationale="y",
    )
    result = apply_reroute(decision)
    assert result["audit_log"][0]["agent"] == "reroute"
