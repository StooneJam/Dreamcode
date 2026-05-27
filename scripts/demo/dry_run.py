"""Plumbing 验证脚本 —— mock 所有 LLM + Collector / Insight ReAct，秒级跑 graph 主线。

不调真 LLM、不联网、不写真 cache（强制 CCA_CACHE_MODE=off 防 mock 数据污染）。
作用：CI smoke test、改图后快速验证连接性。

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
    TaskPlan,
    TaskPlanOutput,
    UserSentiment,
)

from cca.demo._common import hr, show_decisions, summary


# ── fake LLM 工厂 ──────────────────────────────────────────────────────


class _FakeStructured:
    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):  # noqa: ANN001
        return self._response


class _FakePMClient:
    """覆盖 with_structured_output 的最小 PM client。"""

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


# ── fake ReAct messages ────────────────────────────────────────────────


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
        sentiment = UserSentiment(
            appstore_cn_rating=4.0, appstore_cn_review_count=10000,
            positive_themes=["界面简洁"], negative_themes=["偶发卡顿"],
        )
        out.append(AIMessage(content=f"(dry-run mock) {n} 情感完成"))
        out.append(ToolMessage(
            content=json.dumps({"product_name": n, "sentiment": sentiment.model_dump()}, ensure_ascii=False),
            tool_call_id="dry-run", name="finalize_sentiment",
        ))
    return out


def _patch_all() -> None:
    """patch PM + collector + insight 的 LLM 入口。"""
    import cca.agents.pm as pm_mod
    pm_mod.gpt = _FakePMClient(_pm_responses())  # type: ignore[assignment]

    # Collector exploration_node: mock create_react_agent
    import cca.agents.collector as col_mod
    explore_agent = MagicMock()
    explore_agent.invoke.return_value = {"messages": _collector_exploration_msgs()}
    col_mod.create_react_agent = lambda _bound=explore_agent, **_k: _bound  # type: ignore[assignment]

    # Collector phase 2: 直接替换 collect_one_product 返回固定 Profile
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

    # Insight: mock create_react_agent，但 collector / insight 共享 langgraph 模块所以分开 patch
    import cca.agents.insight as ins_mod
    insight_agent = MagicMock()
    insight_agent.invoke.return_value = {"messages": _insight_msgs(["钉钉", "企业微信"])}
    ins_mod.create_react_agent = lambda _bound=insight_agent, **_k: _bound  # type: ignore[assignment]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skip-report", action="store_true", default=True,
                   help="dry-run 默认跳过 report（report ReAct 不好 mock）")
    args = p.parse_args()

    # dry-run 时强制 cache=off，避免 mock 数据写进真 cache
    os.environ["CCA_CACHE_MODE"] = "off"
    print("[dry-run] CCA_CACHE_MODE=off（防 mock 污染 cache）", flush=True)

    _patch_all()
    print("[dry-run] PM / Collector / Insight 全部 mock\n", flush=True)

    graph = build_graph(include_report=not args.skip_report)
    state = empty_state("帮我分析飞书的主要竞品", "飞书")

    hr("DRY-RUN · plumbing 验证")
    result = graph.invoke(state, config={"recursion_limit": 30})

    show_decisions(result.get("decision_log") or [])
    summary(result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
