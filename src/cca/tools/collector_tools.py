"""Collector Agent 专用工具 —— 模块级 @tool，供 create_react_agent 注册。

工具列表：
  finalize_exploration  — 提交一轮探索的 CollectorExplorationResult 结论（ReAct 终态产出）
  challenge_pm          — 向 PM 发出挑战信号（AgentSignal，from_agent="collector"）

注：from_agent 硬编码为 "collector"，跟 Insight 的同名工具区分；
ChallengePayload 强类型，evidence min_length=1，零证据挑战会被 Pydantic 拒。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from cca.schema import AgentSignal, ChallengePayload, CollectorExplorationResult


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
