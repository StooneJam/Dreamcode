"""Analyst Agent 专用工具 —— 模块级 @tool，供 create_react_agent 注册。

工具列表：
  submit_dimension_ranking  — 提交单维度跨产品横向排序
  finalize_swot             — 提交单产品 SWOT 分析结论到 state.profiles
  challenge_pm              — 挑战 PM 的 AnalystTask（事实性 / 主观性）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from cca.schema import AgentSignal, ChallengePayload, SWOT


class RankingEntry(BaseModel):
    """单产品在某维度的排名条目。"""

    product_name: str
    rank: int = Field(ge=1, description="排名，1 为最优")
    note: str = Field(description="一句话说明排名依据，不超过 50 字")


@tool
def submit_dimension_ranking(dimension_name: str, rankings_json: str) -> str:
    """提交单维度下所有产品的横向排序，供报告和 PM 审阅。

    Args:
        dimension_name: 维度名称，如 "视频会议人数上限"
        rankings_json: JSON 数组，每项 {"product_name": str, "rank": int, "note": str}
            rank=1 表示该维度最优，note 引用对应事实（不超过 50 字）
    """
    entries = [RankingEntry(**e) for e in json.loads(rankings_json)]
    return json.dumps(
        {"dimension": dimension_name, "ranking": [e.model_dump() for e in entries]},
        ensure_ascii=False,
    )


@tool
def finalize_swot(product_name: str, swot_json: str) -> str:
    """提交单产品的 SWOT 分析结论，写入 profiles.swot。

    每个产品**必须调用本工具一次**，才能把 SWOT 落到 state.profiles。

    Args:
        product_name: 产品名，必须在 analyst_task.product_names 中
        swot_json: 符合 SWOT schema 的 JSON 字符串。四象限各至少 1 条 SWOTPoint：
            strengths / weaknesses / opportunities / threats
            每条 SWOTPoint.supporting_fact_statements 至少 1 项，
            引用 profiles 中 dimensions.facts.statement 的原文（逐字匹配）
    """
    swot = SWOT.model_validate_json(swot_json)
    return json.dumps(
        {"product_name": product_name, "swot": swot.model_dump()},
        ensure_ascii=False,
    )


@tool
def challenge_pm(
    claim: str,
    evidence: list[str],
    suggested_fix: str | None = None,
    requires_debate: bool = False,
) -> str:
    """发现 PM 下发的 AnalystTask 有错误或不合理时，向 PM 发出挑战信号。

    适用场景：
    - product_names 中某产品在 profiles 中完全缺失（事实性，requires_debate=False）
    - focus_dimensions 中有不适合该产品领域的维度（主观，requires_debate=True）
    - require_swot=True 但某产品数据不足以支撑 SWOT（事实性，requires_debate=False）

    Args:
        claim: 挑战的核心陈述，一句话说清问题
        evidence: 支撑 claim 的事实列表，至少 1 条
        suggested_fix: 可选，建议的修订方向
        requires_debate: 主观判断分歧时为 True；事实性错误为 False
    """
    signal = AgentSignal(
        from_agent="analyst",
        kind="pm_challenge",
        target="analyst_task",
        payload=ChallengePayload(
            claim=claim,
            evidence=evidence,
            suggested_fix=suggested_fix,
        ),
        requires_debate=requires_debate,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()
