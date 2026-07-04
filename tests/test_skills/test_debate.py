"""Tests for the debate skill's flow (no real API calls).

Positions are injected externally by the caller; debate only handles Critique -> Refine -> Judge/Converge.
"""
from __future__ import annotations

import pytest

from cca.schema import DebatePosition, DebateResult, DebateRound, TaskPlan
from cca.skills import debate


class _FakeMessage:
    """Simulates a langchain AIMessage, returned by .invoke()."""
    def __init__(self, content: str):
        self.content = content


class _FakeStructuredLLM:
    """Simulates the callable returned by ChatOpenAI.with_structured_output()."""

    def __init__(self, responses: list):
        self._responses = responses
        self._i = 0

    def invoke(self, _messages):
        if self._i >= len(self._responses):
            raise RuntimeError(f"FakeLLM 调用次数超过预制响应数 ({len(self._responses)})")
        resp = self._responses[self._i]
        self._i += 1
        return resp


class _FakeLLMClient:
    """Simulates a ChatOpenAI client.

    Supports with_structured_output() -> FakeStructuredLLM; plain invoke(); and
    bind(response_format=...) -- the raw-JSON path `_phase_finalize_converged` takes:
    bind returns an object whose invoke() yields AIMessage(content=JSON), with the
    JSON content serialized from responses_by_target_type[Pydantic schema][0].model_dump().
    """

    def __init__(self, responses_by_target_type: dict[type, list], plain_response: str = ""):
        self._responses = responses_by_target_type
        self._plain = plain_response

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002
        return _FakeStructuredLLM(self._responses.get(target_type, []))

    def invoke(self, _messages):
        return _FakeMessage(self._plain)

    def bind(self, **_kwargs):  # noqa: ANN003
        """Matches _phase_finalize_converged's llm.bind(response_format=...) call.

        Returns an object whose invoke() takes the first pre-set response for a
        registered Pydantic schema, model_dump -> json, wrapped as an AIMessage.
        """
        import json as _json

        responses = self._responses

        # exclude helper schemas like _Critique / _Refinement / DebateResult;
        # pick the last registered schema (usually a revised target like TaskPlan/ReportTask)
        from cca.schema import DebateResult as _DR
        from cca.skills.debate import _Critique as _C, _Refinement as _R

        _AUX = {_C, _R, _DR}

        class _BoundFake:
            def invoke(self_inner, _messages):  # noqa: ANN001
                for schema, items in reversed(list(responses.items())):
                    if schema in _AUX:
                        continue
                    if items and hasattr(items[0], "model_dump"):
                        return _FakeMessage(_json.dumps(items[0].model_dump(), ensure_ascii=False))
                return _FakeMessage("{}")

        return _BoundFake()


def test_run_debate_rejects_judge_in_families() -> None:
    with pytest.raises(ValueError):
        debate.run_debate(
            target="pm_taskplan",
            target_content={"x": 1},
            families=("deepseek", "gpt-5"),
            judge="gpt-5",
            seed_positions={
                "deepseek": DebatePosition(agent_family="deepseek", claim="a", evidence=["e"]),
                "gpt-5": DebatePosition(agent_family="gpt-5", claim="b", evidence=["e"]),
            },
        )


def test_run_debate_full_flow_to_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """still_disagrees=True -> skips the convergence short-circuit, eventually reaches judge."""
    from cca.skills.debate import _Critique, _Refinement

    deepseek_responses = {
        _Critique: [_Critique(critique="ds critiques db")],
        _Refinement: [_Refinement(refinement="ds refined", still_disagrees=True)],
    }
    doubao_responses = {
        _Critique: [_Critique(critique="db critiques ds")],
        _Refinement: [_Refinement(refinement="db refined", still_disagrees=True)],
    }
    gpt_responses = {
        DebateResult: [
            DebateResult(
                target="pm_taskplan",
                rounds=[],
                final_verdict="accepted",
                judge_family="gpt-5",
                judge_rationale="ok",
            )
        ],
    }

    family_clients = {
        "deepseek": _FakeLLMClient(deepseek_responses),
        "doubao": _FakeLLMClient(doubao_responses),
        "gpt-5": _FakeLLMClient(gpt_responses),
    }
    monkeypatch.setattr(debate, "get_llm", lambda family: family_clients[family])

    result = debate.run_debate(
        target="pm_taskplan",
        target_content={"competitors": ["X"]},
        families=("deepseek", "doubao"),
        judge="gpt-5",
        max_rounds=1,
        seed_positions={
            "deepseek": DebatePosition(agent_family="deepseek", claim="ds claim", evidence=["e1"]),
            "doubao": DebatePosition(agent_family="doubao", claim="db claim", evidence=["e2"]),
        },
    )

    assert isinstance(result, DebateResult)
    assert result.final_verdict == "accepted"
    assert result.judge_family == "gpt-5"
    assert result.target == "pm_taskplan"
    assert len(result.rounds) == 1
    rnd: DebateRound = result.rounds[0]
    assert rnd.round == 1
    assert {p.agent_family for p in rnd.positions} == {"deepseek", "doubao"}
    assert "deepseek" in rnd.critiques
    assert "doubao" in rnd.critiques


def test_run_debate_converged_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    """still_disagrees=False -> converges via short-circuit, skipping judge and returning directly.
    revised_output goes through with_structured_output(TaskPlan), and must be a valid TaskPlan dict.
    """
    from cca.skills.debate import _Critique, _Refinement

    revised_plan = TaskPlan(
        target_product="飞书",
        product_type="协作办公SaaS",
        competitor_names=["钉钉", "企业微信"],
        collect_tasks=[],
        insight_tasks=[],
    )

    deepseek_responses = {
        _Critique: [_Critique(critique="ds accepts db")],
        _Refinement: [_Refinement(refinement="ds conceded", still_disagrees=False)],
    }
    # deepseek concedes -> the winner is doubao (fam_b), which produces the revised TaskPlan
    doubao_responses = {
        _Critique: [_Critique(critique="db accepts ds")],
        _Refinement: [_Refinement(refinement="db conceded", still_disagrees=True)],
        TaskPlan: [revised_plan],
    }

    family_clients = {
        "deepseek": _FakeLLMClient(deepseek_responses),
        "doubao": _FakeLLMClient(doubao_responses),
    }
    monkeypatch.setattr(debate, "get_llm", lambda family: family_clients[family])

    result = debate.run_debate(
        target="pm_taskplan",
        target_content={"competitors": ["X"]},
        families=("deepseek", "doubao"),
        judge="gpt-5",
        max_rounds=1,
        seed_positions={
            "deepseek": DebatePosition(agent_family="deepseek", claim="ds", evidence=["e"]),
            "doubao": DebatePosition(agent_family="doubao", claim="db", evidence=["e"]),
        },
    )

    assert result.final_verdict == "accepted_with_revision"
    assert result.judge_family is None  # self-converged, no arbitration
    assert "self-converged" in (result.judge_rationale or "")
    assert len(result.rounds) == 1
    # revised_output is a complete TaskPlan with required fields -- validation wasn't bypassed
    assert result.revised_output is not None
    assert result.revised_output["competitor_names"] == ["钉钉", "企业微信"]
    assert result.revised_output["product_type"] == "协作办公SaaS"
    assert "collect_tasks" in result.revised_output


def test_phase_finalize_converged_default_path_uses_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default three-family path: bind(response_format=json_object) + manual parse + _repair_for_schema.
    target='report' corresponds to ReportTask (which has absorbed the old AnalystTask fields)."""
    import json as _json

    from cca.skills.debate import _phase_finalize_converged
    from cca.schema import ReportTask

    revised = ReportTask(
        target_product="飞书",
        competitors=["钉钉"],
        focus_dimensions=["视频会议"],
    )

    class _BoundFakeLLM:
        def invoke(self, _messages):  # noqa: ANN001
            return _FakeMessage(_json.dumps(revised.model_dump(), ensure_ascii=False))

    class _CapturingClient:
        def bind(self, **_kwargs):  # noqa: ANN003
            return _BoundFakeLLM()

    monkeypatch.setattr(debate, "DEV_DOUBAO_OVERRIDE", False)
    monkeypatch.setattr(debate, "get_llm", lambda family: _CapturingClient())  # noqa: ARG005

    out = _phase_finalize_converged(
        winner_family="deepseek",
        target="report",
        target_content={"target_product": "飞书", "competitors": ["钉钉"]},
        winning_refinement="改成 focus_dimensions = ['视频会议']",
    )
    assert out["target_product"] == "飞书"
    assert out["focus_dimensions"] == ["视频会议"]


def test_phase_finalize_converged_dev_override_uses_function_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dev override path: with_structured_output(function_calling) -- no bind, no manual parse."""
    from cca.skills.debate import _phase_finalize_converged
    from cca.schema import ReportTask

    revised = ReportTask(
        target_product="飞书",
        competitors=["钉钉"],
        focus_dimensions=["视频会议"],
    )
    client = _FakeLLMClient({ReportTask: [revised]})
    monkeypatch.setattr(debate, "DEV_DOUBAO_OVERRIDE", True)
    monkeypatch.setattr(debate, "get_llm", lambda family: client)  # noqa: ARG005

    out = _phase_finalize_converged(
        winner_family="deepseek",
        target="report",
        target_content={"target_product": "飞书", "competitors": ["钉钉"]},
        winning_refinement="改成 focus_dimensions = ['视频会议']",
    )
    assert out["target_product"] == "飞书"
    assert out["focus_dimensions"] == ["视频会议"]


def test_run_debate_two_rounds_propagates_refinement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 2-round debate: round two's position.claim should be round one's refinement.text."""
    from cca.skills.debate import _Critique, _Refinement

    def make_client(fam: str):
        return _FakeLLMClient(
            {
                _Critique: [
                    _Critique(critique=f"{fam} r1 crit"),
                    _Critique(critique=f"{fam} r2 crit"),
                ],
                _Refinement: [
                    _Refinement(refinement=f"{fam} r1 refined", still_disagrees=True),
                    _Refinement(refinement=f"{fam} r2 refined", still_disagrees=True),
                ],
            }
        )

    family_clients = {
        "deepseek": make_client("deepseek"),
        "doubao": make_client("doubao"),
        "gpt-5": _FakeLLMClient(
            {
                DebateResult: [
                    DebateResult(
                        target="pm_taskplan",
                        rounds=[],
                        final_verdict="accepted_with_revision",
                        judge_family="gpt-5",
                        judge_rationale="merged",
                        revised_output={"k": "v"},
                    )
                ]
            }
        ),
    }
    monkeypatch.setattr(debate, "get_llm", lambda family: family_clients[family])

    result = debate.run_debate(
        target="pm_taskplan",
        target_content={"x": 1},
        families=("deepseek", "doubao"),
        judge="gpt-5",
        max_rounds=2,
        seed_positions={
            "deepseek": DebatePosition(agent_family="deepseek", claim="ds initial", evidence=["e"]),
            "doubao": DebatePosition(agent_family="doubao", claim="db initial", evidence=["e"]),
        },
    )

    assert len(result.rounds) == 2
    second_round = {p.agent_family: p.claim for p in result.rounds[1].positions}
    assert second_round["deepseek"] == "deepseek r1 refined"
    assert second_round["doubao"] == "doubao r1 refined"


def test_judge_family_is_forced_by_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the LLM misreports its own family, the code force-overwrites judge_family."""
    from cca.skills.debate import _Critique, _Refinement

    family_clients = {
        "deepseek": _FakeLLMClient(
            {
                _Critique: [_Critique(critique="c")],
                _Refinement: [_Refinement(refinement="r", still_disagrees=True)],
            }
        ),
        "doubao": _FakeLLMClient(
            {
                _Critique: [_Critique(critique="c")],
                _Refinement: [_Refinement(refinement="r", still_disagrees=True)],
            }
        ),
        "gpt-5": _FakeLLMClient(
            {
                DebateResult: [
                    DebateResult(
                        target="pm_taskplan",
                        rounds=[],
                        final_verdict="accepted",
                        judge_family="doubao",  # deliberately wrong, simulating an LLM misreport
                        judge_rationale="x",
                    )
                ]
            }
        ),
    }
    monkeypatch.setattr(debate, "get_llm", lambda family: family_clients[family])

    result = debate.run_debate(
        target="pm_taskplan",
        target_content={},
        families=("deepseek", "doubao"),
        judge="gpt-5",
        max_rounds=1,
        seed_positions={
            "deepseek": DebatePosition(agent_family="deepseek", claim="a", evidence=["e"]),
            "doubao": DebatePosition(agent_family="doubao", claim="b", evidence=["e"]),
        },
    )
    assert result.judge_family == "gpt-5"
