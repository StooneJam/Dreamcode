"""Reporter 内部分析工具 —— 维度横向排序 + SWOT。

Reporter ReAct 按 ReportTask.focus_dimensions 和 require_swot 自主调度。
两工具只校验 + 透传 JSON，不写 state；Reporter 把产出嵌进 MD 正文。
"""
from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from cca.schema import SWOT
from cca.tools._validation import safe_load_list, safe_load_validate


class RankingEntry(BaseModel):
    """单产品在某维度的排名。"""

    product_name: str
    rank: int = Field(ge=1, description="排名，1 为最优")
    note: str = Field(description="一句话说明排名依据，不超过 50 字")


@tool
def submit_dimension_ranking(dimension_name: str, rankings_json: str) -> str:
    """提交单维度跨产品横向排序。rankings_json 每项 {product_name, rank, note}。"""
    entries, err = safe_load_list(rankings_json, RankingEntry)
    if err:
        return err
    return json.dumps(
        {"dimension": dimension_name, "ranking": [e.model_dump() for e in entries]},
        ensure_ascii=False,
    )


@tool
def finalize_swot(product_name: str, swot_json: str) -> str:
    """提交单产品 SWOT。require_swot=True 时 product_names 中每个产品调一次。

    四象限各至少 1 条 SWOTPoint；supporting_fact_statements 必须逐字引用
    profiles 中 dimensions.facts.statement 原文。
    """
    swot, err = safe_load_validate(
        swot_json, SWOT,
        hint=(
            "字段规则提示："
            "\n- strengths / weaknesses / opportunities / threats 各为 SWOTPoint 列表（至少 1 条）"
            "\n- SWOTPoint 必填: point (str), supporting_fact_statements (list[str] 非空)"
        ),
    )
    if err:
        return err
    return json.dumps(
        {"product_name": product_name, "swot": swot.model_dump()},
        ensure_ascii=False,
    )
