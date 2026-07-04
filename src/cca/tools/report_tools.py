"""Reporter's internal analysis tools -- cross-product dimension ranking + SWOT.

Reporter's ReAct loop dispatches these on its own based on ReportTask.focus_dimensions
and require_swot. Both tools only validate + pass through JSON, never write to state;
Reporter embeds the output straight into the MD body.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from cca.schema import SWOT
from cca.tools._validation import safe_load_list, safe_load_validate


class RankingEntry(BaseModel):
    """A single product's rank on one dimension."""

    product_name: str
    rank: int = Field(ge=1, description="Rank, 1 is best")
    note: str = Field(description="One sentence explaining the ranking rationale, under 50 chars")


@tool
def submit_dimension_ranking(dimension_name: str, rankings_json: str) -> str:
    """Submit a cross-product ranking for a single dimension. Each rankings_json item is {product_name, rank, note}."""
    entries, err = safe_load_list(rankings_json, RankingEntry)
    if err:
        return err
    return json.dumps(
        {"dimension": dimension_name, "ranking": [e.model_dump() for e in entries]},
        ensure_ascii=False,
    )


@tool
def finalize_swot(product_name: str, swot_json: str) -> str:
    """Submit a single product's SWOT. Called once per product in product_names when require_swot=True.

    Each of the four quadrants needs at least 1 SWOTPoint; supporting_fact_statements
    must quote profiles' dimensions.facts.statement verbatim.
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
