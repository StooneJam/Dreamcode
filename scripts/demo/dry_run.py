"""Plumbing verification script -- mocks every LLM + Collector/Insight ReAct call, runs the graph's main line instantly.

Never calls a real LLM, never goes online, never writes to the real cache (forces
CCA_CACHE_MODE=off to prevent mock data from polluting it).
Purpose: CI smoke test, quick connectivity check after changing the graph.

Usage:
    $env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
    python scripts/demo/dry_run.py
    python scripts/demo/dry_run.py --skip-report
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, ToolMessage

from cca.graph import build_graph, empty_state
from cca.schema import (
    CollectorExplorationResult,
    CollectTask,
    DecisionRecord,
    InitialBrief,
    InitialBriefOutput,
    InsightTask,
    ReportTask,
    ReportTaskOutput,
    ReviewOutput,
    ReviewUnit,
    TaskPlan,
    TaskPlanOutput,
    UserSentiment,
)

from cca.demo._common import hr, show_decisions, summary


# ── fake LLM factory ─────────────────────────────────────────────────


class _FakeStructured:
    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):  # noqa: ANN001
        return self._response


class _FakePMClient:
    """Minimal PM client overriding with_structured_output."""

    def __init__(self, responses_by_type: dict) -> None:
        self._responses = responses_by_type

    def with_structured_output(self, output_type, method=None):  # noqa: ARG002, ANN001
        return _FakeStructured(self._responses[output_type])


def _pm_responses() -> dict:
    initial = InitialBrief(
        target_product="飞书",
        company_hint="字节跳动",
        user_query="帮我分析飞书的主要竞品",
    )
    return {
        InitialBriefOutput: InitialBriefOutput(
            initial_brief=initial,
            decision_records=[DecisionRecord(
                phase="initial_brief", decision_type="target_product_selection",
                chosen={"target_product": "飞书"},
                rationale="dry-run mock: 用户指定飞书",
                inputs_used=["user_query"],
            )],
        ),
        TaskPlanOutput: TaskPlanOutput(
            task_plan=TaskPlan(
                target_product="飞书", product_type="企业协作平台",
                competitor_names=["钉钉", "企业微信"],
                collect_tasks=[CollectTask(product_name=n) for n in ["钉钉", "企业微信"]],
                insight_tasks=[InsightTask(product_name=n) for n in ["钉钉", "企业微信"]],
            ),
            decision_records=[DecisionRecord(
                phase="task_plan", decision_type="competitor_selection",
                chosen={"competitors": ["钉钉", "企业微信"]},
                rationale="dry-run mock: 头部双雄",
                inputs_used=["exploration_result.competitor_names"],
            )],
        ),
        ReviewOutput: ReviewOutput(
            review_units=[
                ReviewUnit(agent=a, product_name=p, status="passed", retry_count=0)
                for a in ("collector", "insight")
                for p in ("钉钉", "企业微信")
            ],
            decision_records=[DecisionRecord(
                phase="review", decision_type="review_judgement",
                chosen={"verdict": "all_passed"},
                rationale="dry-run mock: 数据完整全部通过",
                inputs_used=["profiles"],
            )],
        ),
        ReportTaskOutput: ReportTaskOutput(
            report_task=ReportTask(
                target_product="飞书", competitors=["钉钉", "企业微信"],
                focus_dimensions=["视频会议", "定价"],
                sections=["执行摘要", "SWOT"],
                target_audience="产品负责人",
                invoke_call_report_reviewer=False,
            ),
            decision_records=[DecisionRecord(
                phase="report_task", decision_type="report_structure",
                chosen={"sections": ["执行摘要", "SWOT"]},
                rationale="dry-run mock: 最小章节",
                inputs_used=["profiles"],
            )],
        ),
    }


# ── fake ReAct messages ──────────────────────────────────────────────


def _collector_exploration_msgs() -> list[Any]:
    exp = CollectorExplorationResult(
        target_product="飞书", product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信"],
        discovered_dimensions=["视频会议", "定价"],
        initial_profiles=[],
        rationale="(dry-run mock)",
    )
    return [
        AIMessage(content="(dry-run mock) 探索完成"),
        ToolMessage(content=exp.model_dump_json(), tool_call_id="dry-run", name="finalize_exploration"),
    ]


def _insight_msgs(names: list[str]) -> list[Any]:
    out: list[Any] = []
    for n in names:
        from cca.schema import ReviewSample
        sentiment = UserSentiment(
            aggregate_rating=4.0, rating_review_count=10000,
            positive_themes=["界面简洁"], negative_themes=["偶发卡顿"],
            representative_reviews=[
                ReviewSample(text=f"{n} 评论 {i}", rating=4, platform="appstore_cn")
                for i in range(3)
            ],
        )
        out.append(AIMessage(content=f"(dry-run mock) {n} 情感完成"))
        out.append(ToolMessage(
            content=json.dumps({"product_name": n, "sentiment": sentiment.model_dump()}, ensure_ascii=False),
            tool_call_id="dry-run", name="finalize_sentiment",
        ))
    return out


def _patch_all() -> None:
    """Patch PM + collector + insight's LLM entry points."""
    import cca.agents.pm as pm_mod
    fake_pm = _FakePMClient(_pm_responses())
    pm_mod.get_llm = lambda _family: fake_pm  # type: ignore[assignment]

    # Collector exploration_node: mock create_react_agent
    import cca.agents.collector as col_mod
    explore_agent = MagicMock()
    explore_agent.invoke.return_value = {"messages": _collector_exploration_msgs()}
    col_mod.create_react_agent = lambda _bound=explore_agent, **_k: _bound  # type: ignore[assignment]

    # Collector phase 2: replace collect_one_product directly, returning a fixed Profile
    def _fake_collect(task, _ctx):
        from cca.schema import (
            Dimension, Evidence, Fact, PricingInfo, PricingTier, ProductProfile,
        )
        ev = Evidence(source_url="https://x.com", snippet="mock", fetched_at="2026-05-27T00:00:00Z")
        prof = ProductProfile(
            product_name=task.product_name,
            product_type="协作办公SaaS",
            dimensions=[Dimension(
                name="视频会议", category="功能",
                facts=[Fact(statement=f"{task.product_name} mock", evidence=[ev])],
            )],
            pricing=PricingInfo(
                has_free_tier=True, pricing_model="per_user",
                tiers=[PricingTier(name="Pro", price_per_user_monthly=30.0, currency="CNY")],
            ),
            sources=[ev],
        )
        return {
            "profiles": {task.product_name: prof.model_dump()},
            "audit_log": [{"agent": "collector", "event": "collect_done",
                           "product_name": task.product_name, "_dry_run_mock": True}],
        }
    col_mod.collect_one_product = _fake_collect  # type: ignore[assignment]

    # Insight: mock create_react_agent; collector/insight share the langgraph module, so patched separately
    import cca.agents.insight as ins_mod
    insight_agent = MagicMock()
    insight_agent.invoke.return_value = {"messages": _insight_msgs(["钉钉", "企业微信"])}
    ins_mod.create_react_agent = lambda _bound=insight_agent, **_k: _bound  # type: ignore[assignment]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skip-report", action="store_true", default=True,
                   help="dry-run 默认跳过 report（report ReAct 不好 mock）")
    p.add_argument("--human-review", action="store_true",
                   help="验证 human_gate interrupt/resume 闭环（canned feedback，零 API）")
    args = p.parse_args()

    # force cache=off during dry-run, to keep mock data out of the real cache
    os.environ["CCA_CACHE_MODE"] = "off"
    print("[dry-run] CCA_CACHE_MODE=off（防 mock 污染 cache）", flush=True)

    _patch_all()
    print("[dry-run] PM / Collector / Insight 全部 mock\n", flush=True)

    state = empty_state("帮我分析飞书的主要竞品", "飞书")
    hr("DRY-RUN · plumbing 验证")

    if args.human_review:
        result = _run_with_human_review(args)
    else:
        graph = build_graph(include_report=not args.skip_report)
        result = graph.invoke(state, config={"recursion_limit": 30})

    show_decisions(result.get("decision_log") or [])
    summary(result)


def _run_with_human_review(args: argparse.Namespace) -> dict:
    """Drive interrupt/resume with canned feedback, verifying the human-in-the-loop
    connectivity end-to-end (zero API calls)."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    os.environ["CCA_HUMAN_REVIEW"] = "1"
    graph = build_graph(include_report=not args.skip_report, checkpointer=MemorySaver())
    config = {"recursion_limit": 30, "configurable": {"thread_id": "dry-run-hr"}}
    state = empty_state("帮我分析飞书的主要竞品", "飞书")

    result = graph.invoke(state, config=config)
    rounds = 0
    while "__interrupt__" in result:
        rounds += 1
        payload = result["__interrupt__"][0].value
        print(f"[dry-run] interrupt #{rounds} hint={payload.get('hint')}", flush=True)
        print(f"[dry-run] profiles digest={payload.get('profiles')}", flush=True)
        result = graph.invoke(Command(resume={"raw_feedback": "钉钉定价补充一下"}), config=config)
    print(f"[dry-run] interrupt 轮数={rounds}（仅一次）", flush=True)
    return result


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
