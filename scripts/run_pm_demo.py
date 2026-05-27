"""PM 三阶段 + Collector + Insight + Report 端到端 demo（不接 LangGraph）。

按需混合 mock 与 live 节点：

    --dry-run           mock 所有 LLM，仅验证 plumbing
    --debate MODE       debate 场景：accept / reject / none
    --skip-report       跳过 Report Agent（节省 token）
    --seed-file PATH    PM phase 1 消化用户上传文档
    --live-explore      真跑 Collector exploration_node
    --live-collect      真跑 Collector collect_node
    --live-insight      真跑 Insight insight_node
    --cache MODE        ReAct 节点缓存：off / write / replay / auto
                        write: 真跑后写缓存；replay: 从缓存重放（demo 现场用）；
                        auto: 命中即重放，未命中真跑+写
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Literal
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, ToolMessage

from cca.schema import (
    AgentSignal,
    ChallengePayload,
    CollectorExplorationResult,
    CollectTask,
    DebateResult,
    DecisionAlternative,
    DecisionRecord,
    Dimension,
    DomainSeed,
    Evidence,
    Fact,
    InitialBrief,
    InitialBriefOutput,
    InsightTask,
    PricingInfo,
    PricingTier,
    ProductProfile,
    ReportTask,
    ReportTaskOutput,
    ReviewSample,
    ReviewUnit,
    TaskPlan,
    TaskPlanOutput,
    UserSentiment,
)
from cca.state import CCAState

DebateScenario = Literal["accept", "reject", "none"]

_ACCUMULATING = {
    "audit_log", "debate_results", "agent_signals", "consumed_signal_ids",
    "decision_log", "review_state", "qa_notes", "qa_results",
}


# ── state helpers ─────────────────────────────────────────────────────


def _empty_state(user_query: str, target_product: str) -> CCAState:
    return {
        "user_query": user_query, "target_product": target_product, "user_files": None,
        "initial_brief": None, "domain_seed": None, "exploration_result": None,
        "competitor_names": [], "task_plan": None, "report_task": None,
        "profiles": {}, "review_state": [], "qa_results": [],
        "report_status": "pending", "report_md": None, "report_pdf_path": None,
        "qa_notes": [], "audit_log": [], "debate_results": [],
        "agent_signals": [], "consumed_signal_ids": [], "decision_log": [],
    }


def _merge(state: CCAState, updates: dict) -> CCAState:
    """简化版 reducer merge：list 字段累加，标量直接覆盖。"""
    for k, v in updates.items():
        if k in _ACCUMULATING and isinstance(v, list):
            state[k] = state.get(k, []) + v  # type: ignore[literal-required]
        else:
            state[k] = v  # type: ignore[literal-required]
    return state


# ── 打印 helpers ───────────────────────────────────────────────────────


def _hr(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def _sub(title: str) -> None:
    print(f"\n  ── {title} ──")


def _dump(label: str, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    indented = "\n".join("    " + line for line in text.splitlines())
    print(f"  {label}:\n{indented}")


def _show_decisions(updates: dict) -> None:
    log = updates.get("decision_log", [])
    if not log:
        return
    _sub(f"DecisionRecord × {len(log)}")
    for d in log:
        print(f"    · [{d['phase']}/{d['decision_type']}] {d['rationale']}")
        for alt in d.get("alternatives_considered") or []:
            print(f"        vs {alt['option']}: {alt['rejected_reason']}")
        if d.get("inputs_used"):
            print(f"        inputs: {d['inputs_used']}")


def _show_debate(result: dict) -> None:
    for rd in result.get("rounds") or []:
        _sub(f"Round {rd.get('round')}")
        for p in rd.get("positions") or []:
            pos = p.model_dump() if hasattr(p, "model_dump") else p
            print(f"    [{pos.get('agent_family')}] {pos.get('claim')}")
            for ev in pos.get("evidence") or []:
                print(f"      · {ev}")
        for fam, text in (rd.get("critiques") or {}).items():
            print(f"    critique > {fam}: {text}")
        for fam, text in (rd.get("refinements") or {}).items():
            print(f"    refine   < {fam}: {text}")


# ── mock 数据 ──────────────────────────────────────────────────────────


_MOCK_HINTS: dict[str, tuple[float, float]] = {
    "钉钉": (4.2, 30.0), "企业微信": (3.9, 25.0),
    "腾讯会议": (4.0, 20.0), "石墨文档": (4.1, 18.0),
}


def _hints(name: str) -> tuple[float, float]:
    return _MOCK_HINTS.get(name, (4.0, 20.0))


def _make_profile(name: str, *, with_sentiment: bool = True) -> dict:
    """Collector + (可选) Insight owner 字段齐全的 profile。SWOT 由 Reporter 工具产，不在此。"""
    rating, price = _hints(name)
    ev = Evidence(
        source_url=f"https://{name}.com/pricing",
        snippet=f"{name} Pro {price}元/用户/月",
        fetched_at="2026-05-25T10:00:00Z",
    )
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
    """一轮探索 mock；含一个故意应被替换的竞品（腾讯会议）。"""
    return {
        "target_product": "飞书",
        "product_type": "企业协作平台",
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
    return [
        ReviewUnit(agent="collector", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(
            agent="collector", product_name="企业微信", status="forced", retry_count=3,
            qa_flags=["定价来源 404，数据不完整"],
        ).model_dump(),
        ReviewUnit(agent="insight", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(agent="insight", product_name="企业微信", status="passed", retry_count=1).model_dump(),
    ]


def _fake_collect_one_product(task: CollectTask, _ctx: dict) -> dict:
    """Dry-run collect_one_product 替身：直接返回 Collector-only profile。"""
    profile = _make_profile(task.product_name, with_sentiment=False)
    return {
        "profiles": {task.product_name: profile},
        "audit_log": [{
            "agent": "collector", "event": "collect_done",
            "product_name": task.product_name,
            "dimensions_count": len(profile["dimensions"]),
            "_dry_run_mock": True,
        }],
    }


# ── debate 信号 ────────────────────────────────────────────────────────


def _debate_signal(scenario: DebateScenario) -> AgentSignal:
    """构造主观挑战信号。accept 场景理由站得住，reject 站不住。"""
    if scenario == "accept":
        payload = ChallengePayload(
            claim="腾讯会议是视频会议工具，不应作为飞书的直接竞品",
            evidence=[
                "腾讯会议核心场景是单点视频会议，不含文档/IM/工作台",
                "飞书定位是一体化协作平台，对齐的竞品是钉钉和企业微信",
                "若必须给第三家，可选石墨文档或 Notion 中国版",
            ],
            suggested_fix="把腾讯会议从竞品列表移除",
        )
    else:  # reject
        payload = ChallengePayload(
            claim="应该把钉钉从竞品列表中移除",
            evidence=[
                "钉钉用户量已经超过 5 亿，是飞书的 10 倍",
                "对比一个体量差距过大的产品没有竞品分析价值",
            ],
            suggested_fix="移除钉钉，专注分析企业微信",
        )
    return AgentSignal(
        from_agent="report", kind="pm_challenge", target="task_plan",
        payload=payload, requires_debate=True,
        ts="2026-05-25T12:00:00+00:00",
    )


# ── dry-run fake LLM ──────────────────────────────────────────────────


class _FakeStructured:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses
        self._i = 0

    def invoke(self, _messages):  # noqa: ANN001
        r = self._responses[self._i]
        self._i += 1
        return r


class _FakeLLM:
    """覆盖 with_structured_output + bind 的最小客户端，给 PM / debate skill 用。"""

    def __init__(self, responses: dict[type, list[Any]]) -> None:
        self._responses = responses

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002, ANN001
        return _FakeStructured(self._responses.get(target_type, []))

    def bind(self, **_kwargs):  # noqa: ANN003
        # _phase_finalize_converged 走 bind(response_format=...) + 手动解 JSON 路径
        from cca.schema import DebateResult as _DR
        from cca.skills.debate import _Critique as _C, _Refinement as _R
        aux = {_C, _R, _DR}
        responses = self._responses

        class _Bound:
            def invoke(_self, _messages):  # noqa: ANN001
                for schema, items in reversed(list(responses.items())):
                    if schema in aux:
                        continue
                    if items and hasattr(items[0], "model_dump"):
                        return AIMessage(content=json.dumps(items[0].model_dump(), ensure_ascii=False))
                return AIMessage(content="{}")

        return _Bound()


def _dry_pm_responses(with_seed: bool) -> dict[type, list[Any]]:
    """PM 三阶段的预制响应；with_seed=True 时附 DomainSeed mock。"""
    initial = InitialBrief(
        target_product="飞书", company_hint="字节跳动",
        user_query="帮我分析飞书的主要竞品",
    )
    seed = DomainSeed(
        source_files=[],
        dimension_candidates=["视频会议", "AI 助手", "定价", "移动端体验"],
        competitor_mentions=["钉钉", "企业微信"],
        product_type_hint="企业协作平台",
        terminology={"DAU": "日活跃用户"},
    ) if with_seed else None
    return {
        InitialBriefOutput: [InitialBriefOutput(
            initial_brief=initial,
            decision_records=[DecisionRecord(
                phase="initial_brief", decision_type="target_product_selection",
                chosen={"target_product": "飞书"},
                rationale="用户明确指定『飞书』，直接采用",
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
                require_swot=True, cross_product_comparison_required=True,
                output_formats=["markdown", "pdf"],
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
    """debate 三阶段预制响应：accept 收敛短路；reject 走 judge 仲裁。"""
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
    else:  # reject
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
            judge_family="doubao",
            judge_rationale="挑战方理由不成立——用户量差距不构成排除竞品的依据",
            revised_output=None,
        )]}
    return {"deepseek": _FakeLLM(ds), "gpt-5": _FakeLLM(gpt5), "doubao": _FakeLLM(doubao)}


def _dry_collector_msgs() -> list[Any]:
    exploration = CollectorExplorationResult(
        target_product="飞书", product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信", "腾讯会议"],
        discovered_dimensions=["视频会议", "文档协作", "AI 助手", "定价"],
        initial_profiles=[],
        rationale="(dry-run mock) 联网发现三家头部协作产品",
    )
    return [
        AIMessage(content="(dry-run mock) 总结探索结果"),
        ToolMessage(content=exploration.model_dump_json(), tool_call_id="dry-run", name="finalize_exploration"),
    ]


def _dry_insight_msgs(names: list[str]) -> list[Any]:
    msgs: list[Any] = []
    for name in names:
        sentiment = UserSentiment(
            appstore_cn_rating=4.0, appstore_cn_review_count=10000,
            positive_themes=["界面简洁", "功能完善"], negative_themes=["偶发卡顿"],
        )
        msgs.append(AIMessage(content=f"(dry-run mock) {name} 情感分析完成"))
        msgs.append(ToolMessage(
            content=json.dumps({"product_name": name, "sentiment": sentiment.model_dump()}, ensure_ascii=False),
            tool_call_id="dry-run", name="finalize_sentiment",
        ))
    return msgs


def _patch_for_dry_run(scenario: DebateScenario, with_seed: bool, *,
                       live_explore: bool, live_insight: bool) -> None:
    """把 PM / debate / Collector / Insight 的 LLM 入口替换为 fake。

    live_collect 在主流程中通过替换 collect_one_product 实现，不在此 patch。
    """
    import cca.agents.pm as pm_mod
    import cca.skills.debate as debate_mod

    pm_mod.gpt = _FakeLLM(_dry_pm_responses(with_seed))  # type: ignore[assignment]
    debate_clients = _dry_debate_clients(scenario)
    debate_mod.get_llm = lambda family: debate_clients[family]  # type: ignore[assignment]

    if live_explore:
        import cca.agents.collector as collector_mod
        collector_agent = MagicMock()
        collector_agent.invoke.return_value = {"messages": _dry_collector_msgs()}
        # 默认参数固化闭包，避免后续同名变量被覆盖
        collector_mod.create_react_agent = lambda _bound=collector_agent, **_k: _bound  # type: ignore[assignment]

    if live_insight:
        import cca.agents.insight as insight_mod
        insight_agent = MagicMock()
        insight_agent.invoke.return_value = {"messages": _dry_insight_msgs(["钉钉", "企业微信", "腾讯会议"])}
        insight_mod.create_react_agent = lambda _bound=insight_agent, **_k: _bound  # type: ignore[assignment]


# ── 主流程 ─────────────────────────────────────────────────────────────


def _run_phase_collector(state: CCAState) -> None:
    """跑 Collector exploration_node（live）。"""
    _hr("COLLECTOR · exploration_node (live)")
    from cca.agents.collector import exploration_node
    _merge(state, exploration_node(state))
    if state.get("exploration_result"):
        _dump("exploration_result", state["exploration_result"])
    else:
        print("  [warn] Collector 未产出 exploration_result")


def _run_phase_collect(state: CCAState) -> None:
    """跑 Collector collect_node（live，逐产品打印进度）。"""
    _hr("COLLECTOR · collect_node (live)")
    import cca.agents.collector as collector_mod
    from cca.state import _merge_profiles as mp

    raw_tasks = (state.get("task_plan") or {}).get("collect_tasks", [])
    sigs: list[dict] = []
    audit: list[dict] = []
    for i, raw in enumerate(raw_tasks, 1):
        task = CollectTask(**raw) if isinstance(raw, dict) else raw
        print(f"  [{i}/{len(raw_tasks)}] 采集 {task.product_name} ...", flush=True)
        ctx = collector_mod._build_per_product_context(state, task.product_name)
        partial = collector_mod.collect_one_product(task, ctx)
        for n, p in (partial.get("profiles") or {}).items():
            state["profiles"] = mp(state.get("profiles", {}), {n: p})
        sigs.extend(partial.get("agent_signals") or [])
        audit.extend(partial.get("audit_log") or [])
    _merge(state, {"agent_signals": sigs, "audit_log": audit})
    state["review_state"] = _mock_review_state()


def _run_phase_insight(state: CCAState) -> None:
    """跑 Insight insight_node（live，profiles 用 _merge_profiles reducer 合并）。"""
    _hr("INSIGHT · insight_node (live)")
    from cca.agents.insight import insight_node
    from cca.state import _merge_profiles as mp

    out = insight_node(state)
    patch = out.get("profiles") or {}
    rest = {k: v for k, v in out.items() if k != "profiles"}
    state["profiles"] = mp(state.get("profiles", {}), patch)
    _merge(state, rest)
    print(f"  情感分析完成 × {len(patch)}：{list(patch.keys())}")


def _run_debate(state: CCAState, scenario: DebateScenario,
                handle_signal_node, read_defense) -> None:
    _hr(f"SIGNAL · debate ({scenario})")
    sig = _debate_signal(scenario)
    _sub("CHALLENGE (from report)")
    print(f"    claim: {sig.payload.claim}")
    for e in sig.payload.evidence:
        print(f"      · {e}")

    defense = read_defense(sig.target, state)
    _sub("DEFENSE (PM 从 decision_log 拼装)")
    print(f"    claim: {defense.claim}")
    for e in defense.evidence:
        print(f"      · {e}")

    state["agent_signals"] = state.get("agent_signals", []) + [sig.model_dump()]
    out = handle_signal_node(state)
    _merge(state, out)

    if out.get("debate_results"):
        r = out["debate_results"][0]
        _sub("DEBATE ROUNDS")
        _show_debate(r)
        _sub("VERDICT")
        print(f"    verdict:  {r['final_verdict']}")
        print(f"    judge:    {r.get('judge_family') or '(self-converged)'}")
        if r.get("revised_output"):
            _dump("revised_output", r["revised_output"])


def run_demo(*, dry_run: bool, scenario: DebateScenario, skip_report: bool,
             seed_file: str | None, live_explore: bool, live_collect: bool,
             live_insight: bool) -> None:
    if dry_run:
        _patch_for_dry_run(
            scenario if scenario != "none" else "accept",
            with_seed=seed_file is not None,
            live_explore=live_explore, live_insight=live_insight,
        )
        if live_collect:
            import cca.agents.collector as collector_mod
            collector_mod.collect_one_product = _fake_collect_one_product  # type: ignore[assignment]
        tags = [t for t, on in [("explore", live_explore), ("collect", live_collect),
                                ("insight", live_insight)] if on]
        print(f"[dry-run] LLM 已 mock{'（含 ' + '+'.join(tags) + '）' if tags else ''}\n")

    # patch 之后再 import，捕获到 fake gpt
    from cca.agents.pm import (
        _read_defense, handle_signal_node, initial_brief_node,
        report_task_node, task_plan_node,
    )

    state = _empty_state("帮我分析飞书的主要竞品", "飞书")
    if seed_file:
        from pathlib import Path
        if not Path(seed_file).exists():
            raise SystemExit(f"--seed-file 路径不存在: {seed_file}")
        state["user_files"] = [seed_file]
        print(f"[input] user_files = [{seed_file}]")

    # PHASE 1
    _hr("PHASE 1 · InitialBrief (+ DomainSeed)")
    _merge(state, out := initial_brief_node(state))
    _dump("initial_brief", state["initial_brief"])
    if state.get("domain_seed"):
        _dump("domain_seed", state["domain_seed"])
    _show_decisions(out)

    # COLLECTOR exploration
    if live_explore:
        _run_phase_collector(state)
        if not state.get("exploration_result"):
            return
    else:
        state["exploration_result"] = _mock_exploration()

    # PHASE 2
    _hr("PHASE 2 · TaskPlan")
    _merge(state, out := task_plan_node(state))
    _dump("task_plan", state["task_plan"])
    _show_decisions(out)

    # debate
    if scenario != "none":
        _run_debate(state, scenario, handle_signal_node, _read_defense)
        if state["task_plan"] is None:
            _hr("流程提前结束")
            print("  task_plan 被 rejected，demo 到此为止。")
            return

    # COLLECTOR phase 2 + INSIGHT
    if live_collect:
        _run_phase_collect(state)
    else:
        state["profiles"] = {
            "钉钉": _make_profile("钉钉"),
            "企业微信": _make_profile("企业微信"),
        }
        state["review_state"] = _mock_review_state()
        state["competitor_names"] = ["钉钉", "企业微信"]

    if live_insight:
        _run_phase_insight(state)

    # PHASE 3
    _hr("PHASE 3 · ReportTask（含原 Analyst 字段）")
    print(f"  profiles: {list(state['profiles'].keys())}")
    print(f"  review_state: {len(state['review_state'])} 条")
    _merge(state, out := report_task_node(state))
    _dump("report_task", state["report_task"])
    _show_decisions(out)

    # REPORT
    if skip_report or dry_run:
        _hr(f"SKIP · report_node ({'--skip-report' if skip_report else 'dry-run'})")
    else:
        _hr("REPORT AGENT · 生成 MD + PDF")
        from cca.agents.qa_report import report_node
        _merge(state, report_node(state))
        print(f"  status: {state['report_status']} | pdf: {state['report_pdf_path']}")
        if state["report_md"]:
            print(f"  md 前 300 字: {state['report_md'][:300].replace(chr(10), ' | ')}...")

    # 终态
    _hr("END · 终态摘要")
    print(f"  decision_log: {len(state['decision_log'])} 条")
    print(f"  debate_results: {len(state['debate_results'])} 条")
    print(f"  audit_log: {len(state['audit_log'])} 条")
    print(f"  consumed_signal_ids: {state['consumed_signal_ids']}")
    print("\n  decision_log 摘要:")
    for d in state["decision_log"]:
        print(f"    [{d.get('decision_id', '?')}] {d['phase']}/{d['decision_type']} — {d['rationale'][:80]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="mock 所有 LLM")
    p.add_argument("--debate", choices=["accept", "reject", "none"], default="accept")
    p.add_argument("--skip-report", action="store_true")
    p.add_argument("--seed-file", type=str, default=None, help="用户上传文档路径（.pdf/.txt/.md）")
    p.add_argument("--live-explore", "--live-collector", action="store_true")
    p.add_argument("--live-collect", action="store_true")
    p.add_argument("--live-insight", action="store_true")
    p.add_argument(
        "--cache",
        choices=["off", "write", "replay", "auto"],
        default=None,
        help="ReAct 节点缓存模式（覆盖 CCA_CACHE_MODE 环境变量）",
    )
    args = p.parse_args()

    # dry-run 用 mock LLM，写入的 cache 跟真 LLM 数据不可互换 —— 强制关闭 cache
    # 避免后续真 LLM 跑时误命中 mock 缓存。
    if args.dry_run and args.cache and args.cache != "off":
        print(f"[cache] WARN: --dry-run 强制 cache=off（避免 mock 数据污染真 LLM cache，原值 --cache={args.cache} 被忽略）")
        args.cache = "off"

    if args.cache is not None:
        import os
        os.environ["CCA_CACHE_MODE"] = args.cache
        print(f"[cache] mode={args.cache}")

    try:
        run_demo(
            dry_run=args.dry_run, scenario=args.debate, skip_report=args.skip_report,
            seed_file=args.seed_file, live_explore=args.live_explore,
            live_collect=args.live_collect, live_insight=args.live_insight,
        )
    except KeyboardInterrupt:
        print("\n[中断]")
        sys.exit(130)


if __name__ == "__main__":
    main()
