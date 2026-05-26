"""PM Agent + Collector + Report Agent end-to-end demo.

直接调用 PM 4 个阶段节点 + handle_signal_node + (可选) Collector exploration_node
+ report_node，不接 LangGraph。
上游产出（exploration_result / profiles / review_state）默认用硬编码 mock 喂入；
传 `--live-collector` 后 phase 2 之前会真调 Collector 联网探索；
传 `--seed-file PATH` 让 PM phase 1 消化用户上传的文档（D-032 修订版路径）。

Usage:
    env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"    防止中文乱码
    python scripts/run_pm_demo.py --dry-run                # mock 所有 LLM，验证 plumbing
    python scripts/run_pm_demo.py                          # 真 LLM 调用 (debate=accept)
    python scripts/run_pm_demo.py --debate reject          # 跑会被 PM 拒掉的 debate 场景
    python scripts/run_pm_demo.py --debate none --skip-report  # 只跑 4 阶段
    python scripts/run_pm_demo.py --seed-file docs/market.md   # PM phase 1 消化用户文档
    python scripts/run_pm_demo.py --live-collector             # 真跑 Collector exploration_node
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Literal

from cca.schema import (
    AgentSignal,
    AnalystTask,
    AnalystTaskOutput,
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
    SWOT,
    SWOTPoint,
    TaskPlan,
    TaskPlanOutput,
    UserSentiment,
)
from cca.state import CCAState

DebateScenario = Literal["accept", "reject", "none"]


# ── helpers ────────────────────────────────────────────────────────────


def _empty_state(user_query: str, target_product: str) -> CCAState:
    return {
        "user_query": user_query,
        "target_product": target_product,
        "user_files": None,
        "initial_brief": None,
        "domain_seed": None,
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
        "consumed_signal_ids": [],
        "decision_log": [],
    }


_ACCUMULATING = {
    "audit_log",
    "debate_results",
    "agent_signals",
    "consumed_signal_ids",
    "decision_log",
    "review_state",
    "qa_notes",
    "qa_results",
}


def _merge(state: CCAState, updates: dict) -> CCAState:
    """简化版 reducer merge：list 字段累加，标量字段直接覆盖。"""
    for k, v in updates.items():
        if k in _ACCUMULATING and isinstance(v, list):
            state[k] = state.get(k, []) + v  # type: ignore[literal-required]
        else:
            state[k] = v  # type: ignore[literal-required]
    return state


def _hr(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def _sub(title: str) -> None:
    print(f"\n  ── {title} ──")


def _dump_json(label: str, data: Any, indent: int = 4) -> None:
    """打印任意 JSON 可序列化对象，便于看 task 全字段。"""
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    indented = "\n".join(" " * indent + line for line in text.splitlines())
    print(f"  {label}:")
    print(indented)


def _show_decisions(updates: dict) -> None:
    log = updates.get("decision_log", [])
    if not log:
        return
    _sub(f"DecisionRecord × {len(log)}")
    for d in log:
        print(f"    · [{d['phase']}/{d['decision_type']}] {d['rationale']}")
        for alt in d.get("alternatives_considered", []) or []:
            print(f"        vs {alt['option']}: {alt['rejected_reason']}")
        if d.get("inputs_used"):
            print(f"        inputs: {d['inputs_used']}")


def _show_debate_position(label: str, pos: Any) -> None:
    """打印一个 DebatePosition (object 或 dict 都接受)。"""
    if hasattr(pos, "model_dump"):
        pos = pos.model_dump()
    print(f"    [{label}] ({pos.get('agent_family')})")
    print(f"      claim:    {pos.get('claim')}")
    for ev in pos.get("evidence", []) or []:
        print(f"      evidence: - {ev}")


def _show_debate_rounds(result: dict) -> None:
    """打印 debate 的每轮 positions / critiques / refinements。"""
    rounds = result.get("rounds") or []
    if not rounds:
        print("    (无 rounds 数据，可能 LLM 直接给出 verdict)")
        return
    for rd in rounds:
        _sub(f"Round {rd.get('round')}")
        for p in rd.get("positions", []) or []:
            _show_debate_position("position", p)
        critiques = rd.get("critiques", {}) or {}
        refinements = rd.get("refinements", {}) or {}
        if critiques:
            print(f"    critiques (key = 被批驳方):")
            for fam, text in critiques.items():
                print(f"      → {fam}: {text}")
        if refinements:
            print(f"    refinements (key = 修订方):")
            for fam, text in refinements.items():
                print(f"      ← {fam}: {text}")


# ── mock 上游产出 ──────────────────────────────────────────────────────


def _mock_exploration_result() -> dict:
    """模拟 Collector 一轮探索的产出。包含一个故意"应被替换"的竞品（腾讯会议）。"""
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


def _evidence(url: str, snippet: str) -> Evidence:
    return Evidence(source_url=url, snippet=snippet, fetched_at="2026-05-25T10:00:00Z")


def _make_profile(name: str, rating: float, price: float) -> dict:
    ev = _evidence(f"https://{name}.com/pricing", f"{name} Pro {price}元/用户/月")
    fact = Fact(statement=f"{name} Pro 版按用户每月 {price} 元", evidence=[ev])
    dimension = Dimension(
        name="视频会议人数上限",
        category="功能",
        facts=[fact],
        cross_product_note=f"{name} 最大支持 300 人视频会议",
    )
    pricing = PricingInfo(
        has_free_tier=True,
        pricing_model="per_user",
        tiers=[PricingTier(name="Pro", price_per_user_monthly=price, currency="CNY")],
    )
    sentiment = UserSentiment(
        appstore_cn_rating=rating,
        appstore_cn_review_count=12000,
        positive_themes=["界面简洁", "通知及时"],
        negative_themes=["偶发卡顿"],
        representative_reviews=[
            ReviewSample(text="整体好用，偶尔卡顿", rating=4, platform="appstore_cn")
        ],
    )
    swot = SWOT(
        strengths=[SWOTPoint(
            point="定价低于竞品均值",
            supporting_fact_statements=[f"{name} Pro 版按用户每月 {price} 元"],
        )],
        weaknesses=[SWOTPoint(
            point="移动端稳定性待提升",
            supporting_fact_statements=["偶发卡顿"],
        )],
        opportunities=[SWOTPoint(
            point="AI 集成场景增长",
            supporting_fact_statements=[f"{name} Pro 版按用户每月 {price} 元"],
        )],
        threats=[SWOTPoint(
            point="头部厂商竞争加剧",
            supporting_fact_statements=["偶发卡顿"],
        )],
    )
    return ProductProfile(
        product_name=name,
        company=f"{name} Inc.",
        website=f"https://{name}.com",
        product_type="协作办公SaaS",
        target_users="中小企业团队",
        dimensions=[dimension],
        pricing=pricing,
        sentiment=sentiment,
        swot=swot,
        sources=[ev],
    ).model_dump()


def _mock_profiles_for_phase_3_4() -> dict[str, dict]:
    return {
        "钉钉": _make_profile("钉钉", rating=4.2, price=30.0),
        "企业微信": _make_profile("企业微信", rating=3.9, price=25.0),
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
        ReviewUnit(agent="analyst", product_name="钉钉", status="passed", retry_count=0).model_dump(),
        ReviewUnit(agent="analyst", product_name="企业微信", status="passed", retry_count=0).model_dump(),
    ]


# ── debate 场景 ────────────────────────────────────────────────────────


def _debate_signal_accept() -> AgentSignal:
    """合理挑战：腾讯会议品类不对齐，应换成更直接的协作平台。预期 verdict=accepted_with_revision。"""
    return AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="task_plan",
        payload=ChallengePayload(
            claim="腾讯会议是视频会议工具，不应作为飞书的直接竞品",
            evidence=[
                "腾讯会议核心场景是单点视频会议，不含文档/IM/工作台",
                "飞书定位是一体化协作平台，对齐的竞品是钉钉和企业微信",
                "若必须给第三家，可选石墨文档或 Notion 中国版（同为协作产品）",
            ],
            suggested_fix="把腾讯会议从竞品列表移除",
        ),
        requires_debate=True,
        ts="2026-05-25T12:00:00+00:00",
    )


def _debate_signal_reject() -> AgentSignal:
    """站不住脚的挑战：因为钉钉用户量大就该排除。预期 verdict=rejected。"""
    return AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="task_plan",
        payload=ChallengePayload(
            claim="应该把钉钉从竞品列表中移除",
            evidence=[
                "钉钉用户量已经超过 5 亿，是飞书的 10 倍",
                "对比一个体量差距过大的产品没有竞品分析价值",
            ],
            suggested_fix="移除钉钉，专注分析企业微信",
        ),
        requires_debate=True,
        ts="2026-05-25T12:01:00+00:00",
    )


# ── dry-run 时的 LLM mock ──────────────────────────────────────────────


class _FakeStructuredLLM:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses
        self._i = 0

    def invoke(self, _messages):  # noqa: ANN001
        if self._i >= len(self._responses):
            raise RuntimeError(f"FakeLLM 调用次数超过预制响应 ({len(self._responses)})")
        r = self._responses[self._i]
        self._i += 1
        return r


class _FakePMClient:
    """按 target_type 派发预制响应，模拟 pm.gpt。"""

    def __init__(self, responses_by_type: dict[type, list[Any]]) -> None:
        self._responses = responses_by_type

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002, ANN001
        return _FakeStructuredLLM(self._responses.get(target_type, []))


def _build_dry_run_pm_responses(
    scenario: DebateScenario, with_seed: bool = False
) -> dict[type, list[Any]]:
    """凑齐 PM 4 个节点的预制响应。debate finalize 走 debate skill，不在这里 mock。

    with_seed=True 时，InitialBriefOutput 会附带 mock 的 DomainSeed
    （模拟 PM 消化用户上传文档后产出的领域 hint）。
    """
    initial_brief = InitialBrief(
        target_product="飞书",
        company_hint="字节跳动",
        user_query="帮我分析飞书的主要竞品",
    )
    initial_decisions = [
        DecisionRecord(
            phase="initial_brief",
            decision_type="target_product_selection",
            chosen={"target_product": "飞书"},
            rationale="用户明确指定『飞书』，直接采用",
            inputs_used=["user_query"],
        ),
    ]
    mock_domain_seed = (
        DomainSeed(
            source_files=[],  # 代码端会覆盖
            dimension_candidates=["视频会议", "AI 助手", "定价", "移动端体验"],
            competitor_mentions=["钉钉", "企业微信"],
            product_type_hint="企业协作平台",
            terminology={"DAU": "日活跃用户"},
        )
        if with_seed
        else None
    )
    return {
        InitialBriefOutput: [
            InitialBriefOutput(
                initial_brief=initial_brief,
                decision_records=initial_decisions,
                domain_seed=mock_domain_seed,
            ),
        ],
        TaskPlanOutput: [
            TaskPlanOutput(
                task_plan=TaskPlan(
                    target_product="飞书",
                    product_type="企业协作平台",
                    competitor_names=["钉钉", "企业微信", "腾讯会议"],
                    collect_tasks=[
                        CollectTask(product_name=n) for n in ["钉钉", "企业微信", "腾讯会议"]
                    ],
                    insight_tasks=[
                        InsightTask(product_name=n) for n in ["钉钉", "企业微信", "腾讯会议"]
                    ],
                ),
                decision_records=[
                    DecisionRecord(
                        phase="task_plan",
                        decision_type="competitor_selection",
                        chosen={"competitors": ["钉钉", "企业微信", "腾讯会议"]},
                        alternatives_considered=[
                            DecisionAlternative(
                                option="石墨文档",
                                rejected_reason="市占率低于头部，优先选用户基数大的对照",
                            ),
                        ],
                        rationale="exploration 列出三家头部产品，全部采纳",
                        inputs_used=["exploration_result.competitor_names"],
                    ),
                ],
            ),
        ],
        AnalystTaskOutput: [
            AnalystTaskOutput(
                analyst_task=AnalystTask(
                    product_names=["飞书", "钉钉", "企业微信"],
                    focus_dimensions=["视频会议人数上限", "定价"],
                    require_swot=True,
                ),
                decision_records=[
                    DecisionRecord(
                        phase="analyst_task",
                        decision_type="analyst_focus",
                        chosen={"focus_dimensions": ["视频会议人数上限", "定价"]},
                        rationale="profiles 中视频会议人数和定价的数据完整度最高",
                        inputs_used=["profiles.*.dimensions", "profiles.*.pricing"],
                    ),
                ],
            ),
        ],
        ReportTaskOutput: [
            ReportTaskOutput(
                report_task=ReportTask(
                    target_product="飞书",
                    competitors=["钉钉", "企业微信"],
                    output_formats=["markdown", "pdf"],
                    target_audience="产品负责人",
                    sections=["执行摘要", "核心功能对比", "定价结构", "SWOT 分析", "结论与建议"],
                    invoke_call_report_reviewer=False,
                ),
                decision_records=[
                    DecisionRecord(
                        phase="report_task",
                        decision_type="report_structure",
                        chosen={"sections": ["执行摘要", "核心功能对比", "定价结构", "SWOT 分析", "结论与建议"]},
                        rationale="按 SWOT 高亮项 + 用户最关心的功能/定价组织",
                        inputs_used=["profiles.*.swot"],
                    ),
                ],
            ),
        ],
    }


class _FakeFamilyLLM:
    """模拟单个家族客户端，覆盖 debate skill 调用的 with_structured_output。"""

    def __init__(self, responses: dict[type, list[Any]]) -> None:
        self._responses = responses

    def with_structured_output(self, target_type, method=None):  # noqa: ARG002, ANN001
        return _FakeStructuredLLM(self._responses.get(target_type, []))


def _build_dry_run_debate_clients(scenario: DebateScenario) -> dict[str, _FakeFamilyLLM]:
    """预制 debate 3 阶段的响应：critique → refine → judge / finalize。"""
    from cca.skills.debate import _Critique, _Refinement

    if scenario == "accept":
        deepseek = {
            _Critique: [_Critique(critique="ds 批驳 PM：腾讯会议确实不对齐")],
            _Refinement: [_Refinement(refinement="ds 接受对方观点，应替换", still_disagrees=True)],
        }
        gpt5 = {
            _Critique: [_Critique(critique="gpt 反驳挑战：保留以示行业关联")],
            _Refinement: [_Refinement(refinement="gpt 让步：同意移除", still_disagrees=False)],
            # PM 让步 → 赢家是 deepseek (fam_a)，由 deepseek 产 revised TaskPlan
        }
        deepseek[TaskPlan] = [TaskPlan(  # type: ignore[index]
            target_product="飞书",
            product_type="企业协作平台",
            competitor_names=["钉钉", "企业微信"],  # 腾讯会议已移除
            collect_tasks=[CollectTask(product_name=n) for n in ["钉钉", "企业微信"]],
            insight_tasks=[InsightTask(product_name=n) for n in ["钉钉", "企业微信"]],
        )]
        doubao = {}  # 收敛短路，judge 不上场
    else:  # reject
        deepseek = {
            _Critique: [_Critique(critique="ds 批驳：用户量大不是排除理由")],
            _Refinement: [_Refinement(refinement="ds 坚持立场", still_disagrees=True)],
        }
        gpt5 = {
            _Critique: [_Critique(critique="gpt 反驳：钉钉是直接竞品")],
            _Refinement: [_Refinement(refinement="gpt 维持原选择", still_disagrees=True)],
        }
        doubao = {
            DebateResult: [
                DebateResult(
                    target="pm_taskplan",
                    rounds=[],
                    final_verdict="rejected",
                    judge_family="doubao",
                    judge_rationale="挑战方理由不成立——用户量差距不构成排除竞品的依据",
                    revised_output=None,
                ),
            ],
        }

    return {
        "deepseek": _FakeFamilyLLM(deepseek),
        "gpt-5": _FakeFamilyLLM(gpt5),
        "doubao": _FakeFamilyLLM(doubao),
    }


def _build_dry_run_collector_messages() -> list[Any]:
    """模拟 Collector ReAct 跑完后的 messages 链：仅一条 finalize_exploration ToolMessage 足够。

    实际 ReAct 会有 web_search / fetch_url 等多步，但 exploration_node 只看
    finalize_exploration 的输出，所以 mock 一条就行。
    """
    from langchain_core.messages import AIMessage, ToolMessage

    exploration = CollectorExplorationResult(
        target_product="飞书",
        product_type="企业协作平台",
        competitor_names=["钉钉", "企业微信", "腾讯会议"],
        discovered_dimensions=["视频会议", "文档协作", "AI 助手", "定价"],
        initial_profiles=[],
        rationale="（dry-run mock）联网发现三家头部协作产品",
    )
    return [
        AIMessage(content="（dry-run mock）总结探索结果"),
        ToolMessage(
            content=exploration.model_dump_json(),
            tool_call_id="dry-run",
            name="finalize_exploration",
        ),
    ]


def _patch_for_dry_run(
    scenario: DebateScenario, with_seed: bool, live_collector: bool
) -> None:
    """把 PM / debate skill / (可选) Collector 的 LLM 入口替换为 fake。"""
    import cca.agents.pm as pm_mod
    import cca.skills.debate as debate_mod

    pm_mod.gpt = _FakePMClient(  # type: ignore[assignment]
        _build_dry_run_pm_responses(scenario, with_seed=with_seed)
    )

    debate_clients = _build_dry_run_debate_clients(scenario)
    debate_mod.get_llm = lambda family: debate_clients[family]  # type: ignore[assignment]

    if live_collector:
        # 用 mock_agent 替换 create_react_agent；同 test_collector 模式
        from unittest.mock import MagicMock

        import cca.agents.collector as collector_mod

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": _build_dry_run_collector_messages()}
        collector_mod.create_react_agent = lambda **_kw: mock_agent  # type: ignore[assignment]


# ── 主流程 ──────────────────────────────────────────────────────────────


def run_demo(
    dry_run: bool,
    scenario: DebateScenario,
    skip_report: bool,
    seed_file: str | None,
    live_collector: bool,
) -> None:
    if dry_run:
        _patch_for_dry_run(
            scenario if scenario != "none" else "accept",
            with_seed=seed_file is not None,
            live_collector=live_collector,
        )
        print("[dry-run] LLM 调用已 mock"
              + (" (含 Collector ReAct)" if live_collector else "")
              + "\n")

    # 节点函数在 patch 之后再 import，避免捕获到原始 gpt 引用
    from cca.agents.pm import (
        analyst_task_node,
        handle_signal_node,
        initial_brief_node,
        report_task_node,
        task_plan_node,
    )

    state = _empty_state(
        user_query="帮我分析飞书的主要竞品",
        target_product="飞书",
    )
    if seed_file:
        from pathlib import Path
        seed_path = Path(seed_file)
        if not seed_path.exists():
            raise SystemExit(f"--seed-file 路径不存在: {seed_path}")
        state["user_files"] = [str(seed_path)]
        print(f"[input] user_files = [{seed_path}]\n")

    # ── PHASE 1 ──
    _hr("PHASE 1 · InitialBrief (+ DomainSeed)")
    out = initial_brief_node(state)
    state = _merge(state, out)
    _dump_json("initial_brief", state["initial_brief"])
    if state.get("domain_seed"):
        _dump_json("domain_seed (PM 蒸馏自用户文档)", state["domain_seed"])
    elif seed_file:
        print("  [warn] 提供了 --seed-file 但 PM 未产出 domain_seed（见 audit_log）")
    _show_decisions(out)

    # ── COLLECTOR phase 1 (可选) ──（替换 mock exploration_result）──
    if live_collector:
        _hr("COLLECTOR · exploration_node (live)")
        from cca.agents.collector import exploration_node

        out = exploration_node(state)
        state = _merge(state, out)
        if state.get("exploration_result"):
            _dump_json("exploration_result (Collector 联网产出)", state["exploration_result"])
        else:
            print("  [warn] Collector 未产出 exploration_result（finalize_exploration 未调用）")
            print(f"  audit_log 末尾: {out.get('audit_log', [])[-1] if out.get('audit_log') else '(空)'}")
            return  # 没产出，后续 PHASE 2 跑不下去

    # ── PHASE 2 ──
    _hr("PHASE 2 · TaskPlan")
    if not live_collector:
        # 没跑 live Collector，仍用硬编码 mock 喂 exploration_result
        state["exploration_result"] = _mock_exploration_result()
    _dump_json("INPUT · exploration_result", state["exploration_result"])
    out = task_plan_node(state)
    state = _merge(state, out)
    _dump_json("OUTPUT · task_plan", state["task_plan"])
    _show_decisions(out)

    # ── SIGNAL ──（debate 挑战）──
    if scenario != "none":
        _hr(f"SIGNAL · debate ({scenario})")
        sig = _debate_signal_accept() if scenario == "accept" else _debate_signal_reject()
        _sub("CHALLENGE （from analyst）")
        print(f"    claim:    {sig.payload.claim}")
        for e in sig.payload.evidence:
            print(f"    evidence: - {e}")
        if sig.payload.suggested_fix:
            print(f"    suggested_fix: {sig.payload.suggested_fix}")

        # 显式展示 PM 即将进入 debate 时的 defense（从 decision_log 读）
        from cca.agents.pm import _read_defense
        defense = _read_defense(sig.target, state)
        _sub("DEFENSE （PM 从 decision_log 拼装）")
        _show_debate_position("defense", defense)

        state["agent_signals"] = state.get("agent_signals", []) + [sig.model_dump()]
        out = handle_signal_node(state)
        state = _merge(state, out)

        if out.get("debate_results"):
            r = out["debate_results"][0]
            _sub("DEBATE ROUNDS")
            _show_debate_rounds(r)
            _sub("VERDICT")
            print(f"    final_verdict:   {r['final_verdict']}")
            print(f"    judge_family:    {r.get('judge_family') or '(self-converged)'}")
            print(f"    judge_rationale: {r.get('judge_rationale') or ''}")
            if r.get("revised_output"):
                _dump_json("revised_output", r["revised_output"])
        _sub("最终 state 字段")
        print(f"    state.competitor_names: {state['competitor_names']}")
        print(f"    state.task_plan: "
              f"{'<已清空，待重派>' if state['task_plan'] is None else state['task_plan'].get('competitor_names')}")

    # 如果 debate 把 task_plan 清空了（rejected），后续阶段没法跑，提前打住
    if state["task_plan"] is None:
        _hr("流程提前结束")
        print("  task_plan 被 rejected 清空，后续阶段需 PM 重派；demo 到此为止。")
        return

    # ── PHASE 3 ──（喂 mock profiles）──
    _hr("PHASE 3 · AnalystTask")
    state["profiles"] = _mock_profiles_for_phase_3_4()
    state["review_state"] = _mock_review_state()
    state["competitor_names"] = ["钉钉", "企业微信"]  # 与 mock profiles 对齐
    print(f"  INPUT · profiles 包含: {list(state['profiles'].keys())}")
    print(f"  INPUT · review_state 条目数: {len(state['review_state'])}")
    out = analyst_task_node(state)
    state = _merge(state, out)
    _dump_json("OUTPUT · analyst_task", state["analyst_task"])
    _show_decisions(out)

    # ── PHASE 4 ──
    _hr("PHASE 4 · ReportTask")
    out = report_task_node(state)
    state = _merge(state, out)
    _dump_json("OUTPUT · report_task", state["report_task"])
    _show_decisions(out)

    # ── REPORT AGENT ──
    if skip_report:
        _hr("SKIP · report_node (--skip-report)")
    elif dry_run:
        _hr("SKIP · report_node (dry-run 不 mock ReAct 工具循环)")
    else:
        _hr("REPORT AGENT · 生成 MD + PDF")
        from cca.agents.qa_report import report_node

        out = report_node(state)
        state = _merge(state, out)
        print(f"  report_status: {state['report_status']}")
        print(f"  report_pdf:    {state['report_pdf_path']}")
        if state["report_md"]:
            preview = state["report_md"][:300].replace("\n", " ⏎ ")
            print(f"  md 前 300 字: {preview}…")

    # ── 终态摘要 ──
    _hr("END · 终态摘要")
    print(f"  decision_log 共 {len(state['decision_log'])} 条")
    print(f"  debate_results 共 {len(state['debate_results'])} 条")
    print(f"  audit_log 共 {len(state['audit_log'])} 条")
    print(f"  consumed_signal_ids: {state['consumed_signal_ids']}")
    print()
    print("  完整 decision_log（决策档案，供离线 Q&A）:")
    for d in state["decision_log"]:
        did = d.get("decision_id", "?")
        print(f"    [{did}] {d['phase']}/{d['decision_type']} — {d['rationale'][:80]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="mock 所有 LLM，验证 plumbing")
    p.add_argument(
        "--debate",
        choices=["accept", "reject", "none"],
        default="accept",
        help="debate 场景：accept（合理挑战）/ reject（站不住脚的挑战）/ none（跳过）",
    )
    p.add_argument("--skip-report", action="store_true", help="跳过 report agent（节省 token）")
    p.add_argument(
        "--seed-file",
        type=str,
        default=None,
        help="用户上传文档路径（.pdf / .txt / .md）。给定后 PM phase 1 会消化并蒸馏 DomainSeed",
    )
    p.add_argument(
        "--live-collector",
        action="store_true",
        help="phase 2 之前真调 Collector exploration_node，不再走硬编码 mock_exploration_result",
    )
    args = p.parse_args()

    try:
        run_demo(
            dry_run=args.dry_run,
            scenario=args.debate,
            skip_report=args.skip_report,
            seed_file=args.seed_file,
            live_collector=args.live_collector,
        )
    except KeyboardInterrupt:
        print("\n[中断]")
        sys.exit(130)


if __name__ == "__main__":
    main()
