"""Collector Agent 专用工具 —— 模块级 @tool，供 create_react_agent 注册。

工具列表（按 phase 分）：
  Phase 1（exploration_node）:
    finalize_exploration         — 提交一轮探索的 CollectorExplorationResult
    challenge_pm                 — 挑战 PM 的 InitialBrief（事实/主观）

  Phase 2（collect_one_product / collect_node）:
    finalize_profile             — 提交单产品 ProductProfile，写入 state.profiles[name]
    request_product_replacement  — 数据缺失 → 事实性 data_gap 信号，申请换产品

注：from_agent 硬编码为 "collector"，跟 Insight 的同名工具区分；
ChallengePayload 强类型，evidence min_length=1，零证据挑战会被 Pydantic 拒。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from cca.schema import (
    AgentSignal,
    ChallengePayload,
    CollectorExplorationResult,
    ProductProfile,
)


@tool
def finalize_exploration(result_json: str) -> str:
    """提交一轮探索的结论，结束本节点的 ReAct 循环。

    完成所有联网调研后**必须调用本工具一次**才能产出结构化结果。

    Args:
        result_json: 符合 CollectorExplorationResult schema 的 JSON 字符串。必填字段：
            - target_product: 目标产品名（原样回传）
            - product_type: 联网推断的产品赛道（如"企业协作平台"）
            - competitor_names: list[str]，3-5 家头部竞品
            - discovered_dimensions: list[str]，对比维度候选
            - initial_profiles: list[ProductBrief]，每家竞品的最小档案
              （product_name / company / website / product_type）
            可选 rationale: str，说明你为什么选这些竞品/维度，
            **若 fetch_url 遇到错误时务必在此说明换向原因**。
    """
    result = CollectorExplorationResult.model_validate_json(result_json)
    return result.model_dump_json()


@tool
def challenge_pm(
    claim: str,
    evidence: list[str],
    suggested_fix: str | None = None,
    requires_debate: bool = False,
) -> str:
    """发现 PM 给的 InitialBrief 有事实错误或主观分歧时，向 PM 发出挑战信号。

    适用场景：
    - 联网验证发现 PM 的 company_hint 错了（事实性，requires_debate=False）
    - 联网发现 target_product 已停服或不存在（事实性，requires_debate=False）
    - 对 PM 选定 target_product 的合理性有主观分歧（requires_debate=True）

    Args:
        claim: 挑战的核心陈述，一句话讲清"哪里不对"
        evidence: 支撑 claim 的事实/观测/数据点列表，至少 1 条
        suggested_fix: 可选，建议的修订方向
        requires_debate: 主观判断分歧时为 True；事实性错误为 False
    """
    signal = AgentSignal(
        from_agent="collector",
        kind="pm_challenge",
        target="initial_brief",
        payload=ChallengePayload(
            claim=claim,
            evidence=evidence,
            suggested_fix=suggested_fix,
        ),
        requires_debate=requires_debate,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()


# ── Phase 2 工具 ───────────────────────────────────────────────────────


@tool
def finalize_profile(product_name: str, profile_json: str) -> str:
    """提交单产品的 ProductProfile，结束当前产品的 ReAct 循环。

    每个 CollectTask 完成后**必须调用本工具一次**才能把数据落到 state.profiles。

    Args:
        product_name: 产品名，必须与 CollectTask.product_name 一致（作为 state.profiles 的 key）
        profile_json: 符合 ProductProfile schema 的 JSON 字符串。Collector 该填的字段：
            - product_name（与上面参数一致）
            - product_type / target_users / website
            - dimensions: list[Dimension]，每个 Dimension 含 facts (list[Fact])，
              每个 Fact 含 evidence (list[Evidence])，evidence min_length=1
            - pricing: PricingInfo
            - sources: list[Evidence]，本次抓取过的所有有效 URL 聚合
            **不要**填 sentiment（Insight owner）或 swot（Analyst owner）。
            state.profiles 用 _merge_profiles reducer，并发写入只覆盖自己的字段。
    """
    profile = ProductProfile.model_validate_json(profile_json)
    if profile.product_name != product_name:
        # 不一致则以参数为准，防 LLM 拼 JSON 时漏填或写错
        profile = profile.model_copy(update={"product_name": product_name})
    return json.dumps(
        {"product_name": product_name, "profile": profile.model_dump()},
        ensure_ascii=False,
    )


@tool
def request_product_replacement(
    product_name: str,
    reason: str,
    evidence: list[str],
) -> str:
    """当 CollectTask 指定的产品根本无法采集时，向 PM 申请从竞品列表移除该产品。

    适用场景（**事实性，非主观**）：
    - 联网完全搜不到该产品（不存在或名字错误）
    - 官网已 404 / 域名失效 / 产品确认停服
    - 主要功能页/定价页连续 fetch 失败，剩余 fetch 配额耗尽
    - 该产品无任何公开信息可供建立 ProductProfile

    本工具构造 kind=data_gap + target=task_plan 的事实性信号，PM 收到后走
    reroute 流程清空 task_plan 重派。**不要把"觉得这产品不够格"等主观判断
    塞进来**——那是 phase 1 challenge_pm 该做的事。

    Args:
        product_name: 申请移除的产品名
        reason: 一句话讲清"为什么采不到"（如"官网 404，应用商店搜不到"）
        evidence: 支撑 reason 的具体观测，如失败的 URL、搜索零命中的关键词；至少 1 条
    """
    signal = AgentSignal(
        from_agent="collector",
        kind="data_gap",
        target="task_plan",
        payload=ChallengePayload(
            claim=f"产品『{product_name}』数据无法采集：{reason}",
            evidence=evidence,
            suggested_fix=f"从竞品列表移除 {product_name}，可由 PM 选替代品",
        ),
        requires_debate=False,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()
