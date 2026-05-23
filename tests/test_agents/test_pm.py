"""PM Agent 测试（不调真 API）。

覆盖 4 个阶段节点的输出结构，不测试 LLM 内容质量。
"""
from __future__ import annotations

import pytest

from cca.schema import (
    AnalystTask,
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
