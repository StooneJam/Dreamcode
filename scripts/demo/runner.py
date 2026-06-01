"""开发 / 预录用 demo runner。

两种模式：
  - 图模式（默认）：graph.invoke() 一把梭，适合全流程真跑 / cache fill
  - 手工模式（--live-* / --debate 触发）：按阶段单独跑，mock 非 live 阶段，支持 debate 场景

Usage:
    $env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"

    # 图模式
    python scripts/demo/runner.py --cache write
    python scripts/demo/runner.py --cache auto --skip-report
    python scripts/demo/runner.py --seed-file docs/课题介绍.pdf --cache write

    # 手工模式（细粒度开关）
    python scripts/demo/runner.py --live-explore --cache write
    python scripts/demo/runner.py --live-explore --live-collect --live-insight
    python scripts/demo/runner.py --debate accept
    python scripts/demo/runner.py --debate reject --seed-file docs/课题介绍.pdf

    # 真 LLM debate（DeepSeek vs GPT-5 + Doubao 仲裁）
    python scripts/demo/runner.py --debate reject --live-debate --cache write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Literal
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, ToolMessage

from cca.graph import build_graph, empty_state

from cca.demo._common import dump_json, hr, show_decisions, sub, summary
from cca.observability.logger import format_table, track_pipeline_tokens

DebateScenario = Literal["accept", "reject", "none"]


# ── helpers ────────────────────────────────────────────────────────────────


def _dump(label: str, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    indented = "\n".join("    " + line for line in text.splitlines())
    print(f"  {label}:\n{indented}")


def _show_debate(result: dict) -> None:
    for rd in result.get("rounds") or []:
        sub(f"Round {rd.get('round')}")
        for p in rd.get("positions") or []:
            pos = p.model_dump() if hasattr(p, "model_dump") else p
            print(f"    [{pos.get('agent_family')}] {pos.get('claim')}")
            for ev in pos.get("evidence") or []:
                print(f"      · {ev}")
        for fam, text in (rd.get("critiques") or {}).items():
            print(f"    critique > {fam}: {text}")
        for fam, text in (rd.get("refinements") or {}).items():
            print(f"    refine   < {fam}: {text}")


# ── mock 数据（手工模式 mock 阶段用）───────────────────────────────────────


_MOCK_HINTS: dict[str, tuple[float, float]] = {
    "钉钉": (4.2, 30.0), "企业微信": (3.9, 25.0),
    "腾讯会议": (4.0, 20.0), "石墨文档": (4.1, 18.0),
}


def _hints(name: str) -> tuple[float, float]:
    return _MOCK_HINTS.get(name, (4.0, 20.0))


def _make_profile(name: str, *, with_sentiment: bool = True) -> dict:
    from cca.schema import (
        Dimension, Evidence, Fact, PricingInfo, PricingTier, ProductProfile,
        ReviewSample, UserSentiment,
    )
    rating, price = _hints(name)
    ev = Evidence(source_url=f"https://{name}.com/pricing", snippet=f"{name} Pro {price}元/用户/月")
    sentiment = UserSentiment(
        appstore_cn_rating=rating, appstore_cn_review_count=12000,
        positive_themes=["界面简洁", "通知及时"], negative_themes=["偶发卡顿"],
        representative_reviews=[ReviewSample(text="整体好用，偶尔卡顿", rating=4, platform="appstore_cn")],
    ) if with_sentiment else None
    return ProductProfile(
        product_name=name, company=f"{name} Inc.", website=f"https://{name}.com",
        product_type="协作办公SaaS", target_users="中小企业团队",
        dimensions=[Dimension(
            name="视频会议人数上限", category="功能",
            facts=[Fact(statement=f"{name} Pro 版按用户每月 {price} 元", evidence=[ev])],
            cross_product_note=f"{name} 最大支持 300 人视频会议",
        )],
        pricing=PricingInfo(
            has_free_tier=True, pricing_model="per_user",
            tiers=[PricingTier(name="Pro", price_per_user_monthly=price, currency="CNY")],
        ),
        sentiment=sentiment, sources=[ev],
    ).model_dump()


def _mock_exploration() -> dict:
    return {
        "target_product": "飞书", "product_type": "企业协作平台",
        "competitor_names": ["钉钉", "企业微信", "腾讯会议"],
        "discovered_dimensions": ["视频会议", "文档协作", "AI 助手", "定价", "移动端体验"],
        "initial_profiles": [
            {"product_name": "钉钉", "company": "阿里巴巴", "product_type": "企业协作平台"},
            {"product_name": "企业微信", "company": "腾讯", "product_type": "企业协作平台"},
            {"product_name": "腾讯会议", "company": "腾讯", "product_type": "视频会议工具"},
        ],
        "rationale": "钉钉、企业微信为同类协作平台；腾讯会议品类不对齐但常被并列提及",
    }


def _mock_review_state() -> list[dict]:
    from cca.schema import ReviewUnit
    return [
        ReviewUnit(agent="collector", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(
            agent="collector", product_name="企业微信", status="forced", retry_count=3,
            qa_flags=["定价来源 404，数据不完整"],
        ).model_dump(),
        ReviewUnit(agent="insight", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(agent="insight", product_name="企业微信", status="passed", retry_count=1).model_dump(),
    ]


def _fake_collect_one_product(task: Any, _ctx: dict) -> dict:
    profile = _make_profile(task.product_name, with_sentiment=False)
    return {
        "profiles": {task.product_name: profile},
        "audit_log": [{"agent": "collector", "event": "collect_done",
                       "product_name": task.product_name, "_mock": True}],
    }


# ── debate 信号 ────────────────────────────────────────────────────────────


def _debate_signal(scenario: DebateScenario) -> Any:
    from cca.schema import AgentSignal, ChallengePayload
    if scenario == "accept":
        payload = ChallengePayload(
            claim="腾讯会议是视频会议工具，不应作为飞书的直接竞品",
            evidence=[
                "腾讯会议核心场景是单点视频会议，不含文档/IM/工作台",
                "飞书定位是一体化协作平台，对齐的竞品是钉钉和企业微信",
            ],
            suggested_fix="把腾讯会议从竞品列表移除",
        )
    else:
        payload = ChallengePayload(
            claim="应该把钉钉从竞品列表中移除",
            evidence=["钉钉用户量已经超过 5 亿，是飞书的 10 倍", "对比一个体量差距过大的产品没有竞品分析价值"],
            suggested_fix="移除钉钉，专注分析企业微信",
        )
    return AgentSignal(
        from_agent="report", kind="pm_challenge", target="task_plan",
        payload=payload, requires_debate=True,
        ts="2026-05-25T12:00:00+00:00",
    )


# ── mock LLM（手工模式 dry-run 用）─────────────────────────────────────────


class _FakeStructured:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses
        self._i = 0

    def invoke(self, _messages):  # noqa: ANN001
        r = self._responses[self._i]
        self._i += 1
        return r


class _FakeLLM:
    """覆盖 with_structured_output + bind 的假 LLM 客户端。"""

    def __init__(self, responses: dict[type, list[Any]]) -> None:
        self._responses = responses

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002, ANN001
        return _FakeStructured(self._responses.get(target_type, []))

    def bind(self, **_kwargs):  # noqa: ANN003
        responses = self._responses

        class _Bound:
            def invoke(_self, _messages):  # noqa: ANN001
                from cca.schema import DebateResult as _DR
                from cca.skills.debate import _Critique as _C, _Refinement as _R
                aux = {_C, _R, _DR}
                for schema, items in reversed(list(responses.items())):
                    if schema in aux:
                        continue
                    if items and hasattr(items[0], "model_dump"):
                        return AIMessage(content=json.dumps(items[0].model_dump(), ensure_ascii=False))
                return AIMessage(content="{}")

        return _Bound()


def _dry_pm_responses(with_seed: bool) -> dict[type, list[Any]]:
    from cca.schema import (
        CollectTask, DecisionAlternative, DecisionRecord, DomainSeed,
        InitialBrief, InitialBriefOutput, InsightTask, ReportTask,
        ReportTaskOutput, TaskPlan, TaskPlanOutput,
    )
    seed = DomainSeed(
        source_files=[], dimension_candidates=["视频会议", "AI 助手", "定价", "移动端体验"],
        competitor_mentions=["钉钉", "企业微信"], product_type_hint="企业协作平台",
        terminology={"DAU": "日活跃用户"},
    ) if with_seed else None
    return {
        InitialBriefOutput: [InitialBriefOutput(
            initial_brief=InitialBrief(target_product="飞书", company_hint="字节跳动",
                                       user_query="帮我分析飞书的主要竞品"),
            decision_records=[DecisionRecord(
                phase="initial_brief", decision_type="target_product_selection",
                chosen={"target_product": "飞书"}, rationale="用户明确指定飞书",
                inputs_used=["user_query"],
            )],
            domain_seed=seed,
        )],
        TaskPlanOutput: [TaskPlanOutput(
            task_plan=TaskPlan(
                target_product="飞书", product_type="企业协作平台",
                competitor_names=["钉钉", "企业微信", "腾讯会议"],
                collect_tasks=[CollectTask(product_name=n) for n in ["钉钉", "企业微信", "腾讯会议"]],
                insight_tasks=[InsightTask(product_name=n) for n in ["钉钉", "企业微信", "腾讯会议"]],
            ),
            decision_records=[DecisionRecord(
                phase="task_plan", decision_type="competitor_selection",
                chosen={"competitors": ["钉钉", "企业微信", "腾讯会议"]},
                alternatives_considered=[DecisionAlternative(
                    option="石墨文档", rejected_reason="市占率低于头部",
                )],
                rationale="exploration 列出三家头部产品，全部采纳",
                inputs_used=["exploration_result.competitor_names"],
            )],
        )],
        ReportTaskOutput: [ReportTaskOutput(
            report_task=ReportTask(
                target_product="飞书", competitors=["钉钉", "企业微信"],
                product_names=["飞书", "钉钉", "企业微信"],
                focus_dimensions=["视频会议人数上限", "定价"],
                target_audience="产品负责人",
                sections=["执行摘要", "核心功能对比", "定价结构", "SWOT 分析", "结论与建议"],
                invoke_call_report_reviewer=False,
            ),
            decision_records=[
                DecisionRecord(
                    phase="report_task", decision_type="analysis_focus",
                    chosen={"focus_dimensions": ["视频会议人数上限", "定价"]},
                    rationale="profiles 中数据完整度最高的两个维度",
                    inputs_used=["profiles.*.dimensions", "profiles.*.pricing"],
                ),
                DecisionRecord(
                    phase="report_task", decision_type="report_structure",
                    chosen={"sections": ["执行摘要", "核心功能对比", "定价结构", "SWOT 分析", "结论与建议"]},
                    rationale="按数据完整度高的维度 + 用户最关心的功能/定价组织",
                    inputs_used=["profiles.*"],
                ),
            ],
        )],
    }


def _dry_debate_clients(scenario: DebateScenario) -> dict[str, _FakeLLM]:
    from cca.schema import CollectTask, DebateResult, InsightTask, TaskPlan
    from cca.skills.debate import _Critique, _Refinement

    if scenario == "accept":
        ds = {
            _Critique: [_Critique(critique="ds 批驳 PM：腾讯会议确实不对齐")],
            _Refinement: [_Refinement(refinement="ds 接受对方观点，应替换", still_disagrees=True)],
            TaskPlan: [TaskPlan(
                target_product="飞书", product_type="企业协作平台",
                competitor_names=["钉钉", "企业微信"],
                collect_tasks=[CollectTask(product_name=n) for n in ["钉钉", "企业微信"]],
                insight_tasks=[InsightTask(product_name=n) for n in ["钉钉", "企业微信"]],
            )],
        }
        gpt5 = {
            _Critique: [_Critique(critique="gpt 反驳挑战：保留以示行业关联")],
            _Refinement: [_Refinement(refinement="gpt 让步：同意移除", still_disagrees=False)],
        }
        doubao: dict = {}
    else:
        ds = {
            _Critique: [_Critique(critique="ds 批驳：用户量大不是排除理由")],
            _Refinement: [_Refinement(refinement="ds 坚持立场", still_disagrees=True)],
        }
        gpt5 = {
            _Critique: [_Critique(critique="gpt 反驳：钉钉是直接竞品")],
            _Refinement: [_Refinement(refinement="gpt 维持原选择", still_disagrees=True)],
        }
        doubao = {DebateResult: [DebateResult(
            target="pm_taskplan", rounds=[], final_verdict="rejected",
            judge_family="doubao", judge_rationale="挑战方理由不成立——用户量差距不构成排除竞品的依据",
        )]}
    return {"deepseek": _FakeLLM(ds), "gpt-5": _FakeLLM(gpt5), "doubao": _FakeLLM(doubao)}


def _patch_llms_for_dry(
    scenario: DebateScenario, with_seed: bool, *,
    live_explore: bool, live_insight: bool, live_debate: bool = False,
) -> None:
    """把 PM / debate / Collector / Insight 的 LLM 入口替换为 fake。

    live_debate=True 时 PM 和 debate 不 patch，走真 LLM。
    """
    import cca.agents.pm as pm_mod
    import cca.skills.debate as debate_mod

    if not live_debate:
        pm_mod.gpt = _FakeLLM(_dry_pm_responses(with_seed))  # type: ignore[assignment]
        debate_mod.get_llm = lambda family: _dry_debate_clients(scenario)[family]  # type: ignore[assignment]

    if live_explore:
        _patch_collector_react()

    if live_insight:
        _patch_insight_react()


def _patch_collector_react() -> None:
    import cca.agents.collector as col_mod
    agent = MagicMock()
    agent.invoke.return_value = {"messages": [AIMessage(content="(mock)"), ToolMessage(
        content=json.dumps(_mock_exploration(), ensure_ascii=False),
        tool_call_id="mock", name="finalize_exploration",
    )]}
    col_mod.create_react_agent = lambda _b=agent, **_k: _b  # type: ignore[assignment]


def _patch_insight_react() -> None:
    from cca.schema import UserSentiment
    msgs: list[Any] = []
    for name in ["钉钉", "企业微信", "腾讯会议"]:
        sentiment = UserSentiment(appstore_cn_rating=4.0, appstore_cn_review_count=10000,
                                  positive_themes=["界面简洁"], negative_themes=["偶发卡顿"])
        msgs.extend([
            AIMessage(content=f"(mock) {name} 情感分析完成"),
            ToolMessage(
                content=json.dumps({"product_name": name, "sentiment": sentiment.model_dump()}, ensure_ascii=False),
                tool_call_id="mock", name="finalize_sentiment",
            ),
        ])
    import cca.agents.insight as ins_mod
    agent = MagicMock()
    agent.invoke.return_value = {"messages": msgs}
    ins_mod.create_react_agent = lambda _b=agent, **_k: _b  # type: ignore[assignment]


# ── 图模式（默认）─────────────────────────────────────────────────────────────


def _prompt_human_review(payload: dict) -> dict:
    """human_gate interrupt 暂停时，CLI 展示产出摘要并收一次修订意见。"""
    hr("HUMAN REVIEW · 阶段 2.5 修订意见（仅一次）")
    print(f"  {payload.get('hint', '')}", flush=True)
    for row in payload.get("profiles", []):
        print(
            f"    - {row['product_name']}: {len(row['dimensions'])} 维度 {row['dimensions']}"
            f" | {row['review_count']} 评论 | 平台 {row['platforms']}",
            flush=True,
        )
    text = input("  修订意见（直接回车 = 无修订放行）: ").strip()
    return {"raw_feedback": text} if text else {"approved": True}


def _invoke_with_human_review(graph, state: Any, config: dict) -> dict:
    """图模式带人在环：跑到 interrupt 暂停 → CLI 收文本 → Command(resume) 续跑，直到无 interrupt。"""
    from langgraph.types import Command
    result = graph.invoke(state, config=config)
    while "__interrupt__" in result:
        feedback = _prompt_human_review(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=feedback), config=config)
    return result


def _run_graph(args: argparse.Namespace) -> None:
    os.environ["CCA_CACHE_MODE"] = args.cache
    print(f"[runner] CCA_CACHE_MODE={args.cache}", flush=True)

    config: dict = {"recursion_limit": 30}
    if args.human_review:
        from langgraph.checkpoint.memory import MemorySaver
        os.environ["CCA_HUMAN_REVIEW"] = "1"
        graph = build_graph(include_report=not args.skip_report, checkpointer=MemorySaver())
        config["configurable"] = {"thread_id": "demo-human-review"}
        print("[runner] human-review 开启（interrupt/resume 闭环）", flush=True)
    else:
        graph = build_graph(include_report=not args.skip_report)
    state = empty_state(args.user_query, args.target_product, user_files=args.user_files)

    hr(f"RUNNER · graph mode (cache={args.cache})")
    with track_pipeline_tokens() as token_box:
        if args.human_review:
            result = _invoke_with_human_review(graph, state, config)
        else:
            result = graph.invoke(state, config=config)

    if result.get("exploration_result"):
        dump_json("exploration_result", result["exploration_result"])
    if result.get("task_plan"):
        dump_json("task_plan", result["task_plan"])
    if result.get("profiles"):
        # Collector 写 dimensions/pricing/sources/website；Insight 写 sentiment —— 一并 dump
        dump_json("profiles", result["profiles"])
    if result.get("report_task"):
        dump_json("report_task", result["report_task"])
    if result.get("audit_log"):
        # 节点级事件审计，诊断 insight/finalize_sentiment 等中间步骤
        dump_json("audit_log", result["audit_log"])
    show_decisions(result.get("decision_log") or [])
    summary(result)

    if token_box.get("usages"):
        hr("TOKEN 消耗 · 本次 pipeline 按模型")
        print(format_table(token_box["usages"]))


# ── 手工编排模式（--live-* / --debate 触发）─────────────────────────────────


def _run_manual(args: argparse.Namespace) -> None:
    """手工编排：按阶段单独跑，mock 非 live 阶段，支持 debate。"""
    from cca.state import _merge_profiles as mp

    os.environ["CCA_CACHE_MODE"] = args.cache
    print(f"[runner] CCA_CACHE_MODE={args.cache}", flush=True)

    dry = not any([args.live_explore, args.live_collect, args.live_insight])
    has_debate = args.debate != "none"

    if dry and not has_debate:
        # 纯 dry-run：全 mock，走图 plumbing 验证
        _patch_llms_for_dry(args.debate, with_seed=args.seed_file is not None,
                            live_explore=args.live_explore, live_insight=args.live_insight,
                            live_debate=args.live_debate)
        graph = build_graph(include_report=not args.skip_report)
        state = empty_state(args.user_query, args.target_product, user_files=args.user_files)
        hr("RUNNER · dry-run (graph)")
        result = graph.invoke(state, config={"recursion_limit": 30})
        show_decisions(result.get("decision_log") or [])
        summary(result)
        return

    # 混合模式：mock 非 live 阶段，live 阶段真跑
    _patch_llms_for_dry(args.debate, with_seed=args.seed_file is not None,
                        live_explore=args.live_explore, live_insight=args.live_insight,
                        live_debate=args.live_debate)
    if args.live_collect and not args.live_explore:
        _patch_collector_react()

    # PM 相关 import（在 patch 之后，捕获 fake LLM）
    from cca.agents.pm import (
        _read_defense, handle_signal_node, initial_brief_node,
        report_task_node, task_plan_node,
    )

    tags = [t for t, on in [("explore", args.live_explore), ("collect", args.live_collect),
                            ("insight", args.live_insight)] if on]
    print(f"[runner] 手工编排{'（live: ' + '+'.join(tags) + '）' if tags else ''}", flush=True)

    state = empty_state(args.user_query, args.target_product, user_files=args.user_files)

    # ── PHASE 1: InitialBrief ──
    hr("PHASE 1 · InitialBrief (+ DomainSeed)")
    out = initial_brief_node(state)
    _merge(state, out)
    _dump("initial_brief", state["initial_brief"])
    if state.get("domain_seed"):
        _dump("domain_seed", state["domain_seed"])
    show_decisions(out.get("decision_log", []))

    # ── Exploration ──
    if args.live_explore:
        hr("COLLECTOR · exploration_node (live)")
        from cca.agents.collector import exploration_node
        _merge(state, exploration_node(state))
        if state.get("exploration_result"):
            _dump("exploration_result", state["exploration_result"])
        else:
            print("  [warn] exploration 无产出")
            return
    else:
        state["exploration_result"] = _mock_exploration()

    # ── PHASE 2: TaskPlan ──
    hr("PHASE 2 · TaskPlan")
    _merge(state, out := task_plan_node(state))
    _dump("task_plan", state["task_plan"])
    show_decisions(out.get("decision_log", []))

    # ── Debate（若指定）──
    if has_debate:
        hr(f"SIGNAL · debate ({args.debate})")
        sig = _debate_signal(args.debate)
        sub("CHALLENGE")
        print(f"    claim: {sig.payload.claim}")
        for e in sig.payload.evidence:
            print(f"      · {e}")

        defense = _read_defense(sig.target, state)
        sub("DEFENSE (PM 从 decision_log 拼装)")
        print(f"    claim: {defense.claim}")
        for e in defense.evidence:
            print(f"      · {e}")

        state["agent_signals"] = state.get("agent_signals", []) + [sig.model_dump()]
        out = handle_signal_node(state)
        _merge(state, out)

        if out.get("debate_results"):
            r = out["debate_results"][0]
            _show_debate(r)
            sub("VERDICT")
            print(f"    verdict:  {r['final_verdict']}")
            print(f"    judge:    {r.get('judge_family') or '(self-converged)'}")
            if r.get("revised_output"):
                _dump("revised_output", r["revised_output"])

        if state["task_plan"] is None:
            hr("流程提前结束")
            print("  task_plan 被 rejected，demo 到此为止。")
            return

    # ── Collector phase 2 ──
    if args.live_collect:
        hr("COLLECTOR · phase 2 (live)")
        raw_tasks = (state.get("task_plan") or {}).get("collect_tasks", [])
        from cca.schema import CollectTask
        import cca.agents.collector as collector_mod
        for i, raw in enumerate(raw_tasks, 1):
            task = CollectTask(**raw) if isinstance(raw, dict) else raw
            print(f"  [{i}/{len(raw_tasks)}] {task.product_name} ...", flush=True)
            ctx = collector_mod.build_collect_context(state, task.product_name)
            partial = collector_mod.collect_one_product(task, ctx)
            for n, p in (partial.get("profiles") or {}).items():
                state["profiles"] = mp(state.get("profiles", {}), {n: p})
            _merge(state, {k: v for k, v in partial.items() if k != "profiles"})
        state["review_state"] = _mock_review_state()
    else:
        for name in state.get("competitor_names", []):
            state["profiles"][name] = _make_profile(name, with_sentiment=False)
        state["review_state"] = _mock_review_state()

    # ── Insight ──
    if args.live_insight:
        hr("INSIGHT · insight_one_product (live)")
        from cca.schema import InsightTask
        import cca.agents.insight as insight_mod
        insight_raw = (state.get("task_plan") or {}).get("insight_tasks", [])
        done: list[str] = []
        for i, raw in enumerate(insight_raw, 1):
            task = InsightTask(**raw) if isinstance(raw, dict) else raw
            print(f"  [{i}/{len(insight_raw)}] {task.product_name} ...", flush=True)
            ctx = insight_mod.build_insight_context(state, task.product_name)
            partial = insight_mod.insight_one_product(task, ctx)
            for n, p in (partial.get("profiles") or {}).items():
                state["profiles"] = mp(state.get("profiles", {}), {n: p})
                done.append(n)
            _merge(state, {k: v for k, v in partial.items() if k != "profiles"})
        print(f"  情感分析完成 × {len(done)}：{done}")
    else:
        from cca.schema import UserSentiment, ReviewSample
        for name in state.get("competitor_names", []):
            rating, _ = _hints(name)
            if name in state["profiles"]:
                state["profiles"][name]["sentiment"] = UserSentiment(
                    appstore_cn_rating=rating, appstore_cn_review_count=12000,
                    positive_themes=["界面简洁"], negative_themes=["偶发卡顿"],
                    representative_reviews=[ReviewSample(text="整体好用", rating=4, platform="appstore_cn")],
                ).model_dump()

    # ── PHASE 3: ReportTask ──
    hr("PHASE 3 · ReportTask")
    print(f"  profiles: {list(state['profiles'].keys())}")
    print(f"  review_state: {len(state['review_state'])} 条")
    _merge(state, out := report_task_node(state))
    _dump("report_task", state["report_task"])
    show_decisions(out.get("decision_log", []))

    # ── Report ──
    if args.skip_report:
        hr("SKIP · report_node (--skip-report)")
    else:
        hr("REPORT AGENT · 生成 MD + PDF")
        from cca.agents.qa_report import report_node
        _merge(state, report_node(state))
        print(f"  status: {state['report_status']} | pdf: {state['report_pdf_path']}")
        if state["report_md"]:
            from pathlib import Path
            _md_path = Path(f"output/report_{state['report_task']['target_product']}.md")
            _md_path.parent.mkdir(parents=True, exist_ok=True)
            _md_path.write_text(state["report_md"], encoding="utf-8")
            print(f"  md: {_md_path}")
            print(f"  md 前 300 字: {state['report_md'][:300].replace(chr(10), ' | ')}...")

    summary(state)


# ── state helpers ───────────────────────────────────────────────────────────

_ACCUMULATING = {
    "audit_log", "debate_results", "agent_signals", "consumed_signal_ids",
    "decision_log", "review_state", "qa_notes", "qa_results",
}


def _merge(state: dict, updates: dict) -> None:
    for k, v in updates.items():
        if k in _ACCUMULATING and isinstance(v, list):
            state[k] = state.get(k, []) + v
        else:
            state[k] = v


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-product", default="飞书")
    p.add_argument("--user-query", default="帮我分析飞书的主要竞品")
    p.add_argument("--cache", choices=["off", "write", "auto"], default="auto")
    p.add_argument("--skip-report", action="store_true")
    p.add_argument("--seed-file", type=str, default=None, help="用户上传文档路径")
    p.add_argument("--debate", choices=["accept", "reject", "none"], default="none",
                   help="debate 场景：accept/reject 触发跨家族辩论，none 跳过")
    p.add_argument("--live-explore", action="store_true", help="真跑 Collector exploration")
    p.add_argument("--live-collect", action="store_true", help="真跑 Collector phase 2 深采集")
    p.add_argument("--live-insight", action="store_true", help="真跑 Insight 情感分析")
    p.add_argument("--live-debate", action="store_true", help="真跑跨家族 debate（DeepSeek vs GPT-5 + Doubao 仲裁）")
    p.add_argument("--human-review", action="store_true",
                   help="图模式开启阶段 2.5 人在环：interrupt 暂停收一次修订意见（需 checkpointer）")
    args = p.parse_args()

    args.user_files = [args.seed_file] if args.seed_file else None

    needs_manual = args.live_explore or args.live_collect or args.live_insight or args.debate != "none"

    if needs_manual:
        _run_manual(args)
    else:
        _run_graph(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
