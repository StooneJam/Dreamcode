"""测试 debate skill 流程（不调真 API）。

Position 由 caller 外部注入，debate 只负责 Critique → Refine → Judge / Converge。
"""
from __future__ import annotations

import pytest

from cca.schema import DebatePosition, DebateResult, DebateRound, TaskPlan
from cca.skills import debate


class _FakeMessage:
    """模拟 langchain AIMessage，给 .invoke() 返回用。"""
    def __init__(self, content: str):
        self.content = content


class _FakeStructuredLLM:
    """模拟 ChatOpenAI.with_structured_output() 返回的可调用对象。"""

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
    """模拟 ChatOpenAI client。

    支持 with_structured_output() → FakeStructuredLLM，以及 plain invoke()。
    """

    def __init__(self, responses_by_target_type: dict[type, list], plain_response: str = ""):
        self._responses = responses_by_target_type
        self._plain = plain_response

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002
        return _FakeStructuredLLM(self._responses.get(target_type, []))

    def invoke(self, _messages):
        return _FakeMessage(self._plain)


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
    """still_disagrees=True → 不走收敛短路，最终进入 judge。"""
    from cca.skills.debate import _Critique, _Refinement

    deepseek_responses = {
        _Critique: [_Critique(text="ds critiques db")],
        _Refinement: [_Refinement(text="ds refined", still_disagrees=True)],
    }
    doubao_responses = {
        _Critique: [_Critique(text="db critiques ds")],
        _Refinement: [_Refinement(text="db refined", still_disagrees=True)],
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
    """still_disagrees=False → 收敛短路，跳过 judge 直接返回。
    revised_output 走 with_structured_output(TaskPlan)，必须是合规的 TaskPlan dict。
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
        _Critique: [_Critique(text="ds accepts db")],
        _Refinement: [_Refinement(text="ds conceded", still_disagrees=False)],
    }
    # ds 让步 → 赢家是 doubao（fam_b），由 doubao 产出修订版 TaskPlan
    doubao_responses = {
        _Critique: [_Critique(text="db accepts ds")],
        _Refinement: [_Refinement(text="db conceded", still_disagrees=True)],
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
    assert result.judge_family is None  # self-converged，无仲裁
    assert "self-converged" in (result.judge_rationale or "")
    assert len(result.rounds) == 1
    # revised_output 是完整 TaskPlan，包含 required 字段 — 校验没被绕过
    assert result.revised_output is not None
    assert result.revised_output["competitor_names"] == ["钉钉", "企业微信"]
    assert result.revised_output["product_type"] == "协作办公SaaS"
    assert "collect_tasks" in result.revised_output


def test_phase_finalize_converged_dispatches_to_target_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_phase_finalize_converged 必须按 target 选对应 schema 调 with_structured_output。"""
    from cca.skills.debate import _phase_finalize_converged
    from cca.schema import AnalystTask

    captured: dict = {}

    class _CapturingClient:
        def with_structured_output(self, target_type, method=None):  # noqa: ARG002
            captured["schema"] = target_type
            return _FakeStructuredLLM(
                [AnalystTask(product_names=["飞书"], focus_dimensions=["视频会议"])]
            )

    monkeypatch.setattr(debate, "get_llm", lambda family: _CapturingClient())  # noqa: ARG005

    out = _phase_finalize_converged(
        winner_family="deepseek",
        target="analyst_task",
        target_content={"product_names": ["飞书"]},
        winning_refinement="改成 focus_dimensions = ['视频会议']",
    )
    assert captured["schema"] is AnalystTask
    assert out["product_names"] == ["飞书"]
    assert out["focus_dimensions"] == ["视频会议"]


def test_run_debate_two_rounds_propagates_refinement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 轮 debate：第二轮 position.claim 应是第一轮 refinement.text。"""
    from cca.skills.debate import _Critique, _Refinement

    def make_client(fam: str):
        return _FakeLLMClient(
            {
                _Critique: [
                    _Critique(text=f"{fam} r1 crit"),
                    _Critique(text=f"{fam} r2 crit"),
                ],
                _Refinement: [
                    _Refinement(text=f"{fam} r1 refined", still_disagrees=True),
                    _Refinement(text=f"{fam} r2 refined", still_disagrees=True),
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
    """LLM 自报错家族时，代码强制覆盖 judge_family。"""
    from cca.skills.debate import _Critique, _Refinement

    family_clients = {
        "deepseek": _FakeLLMClient(
            {
                _Critique: [_Critique(text="c")],
                _Refinement: [_Refinement(text="r", still_disagrees=True)],
            }
        ),
        "doubao": _FakeLLMClient(
            {
                _Critique: [_Critique(text="c")],
                _Refinement: [_Refinement(text="r", still_disagrees=True)],
            }
        ),
        "gpt-5": _FakeLLMClient(
            {
                DebateResult: [
                    DebateResult(
                        target="pm_taskplan",
                        rounds=[],
                        final_verdict="accepted",
                        judge_family="doubao",  # LLM 故意错填
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
