"""
LangGraph 主图共享状态。
与 Pydantic 领域模型分文件：domain 类在 schema.py，运行时状态在这里。
"""
from __future__ import annotations
from operator import add
from typing import Annotated, Literal, TypedDict


class CCAState(TypedDict):
    """Agent 间共享的工作台。

    profiles 以 product_name 为 key 存 ProductProfile.model_dump()；
    review_state / audit_log / qa_notes 用 add reducer，多节点并发写入自动追加。
    """
    user_query: str
    target_product: str

    competitor_names: list[str]
    task_plan: dict               # TaskPlan.model_dump()

    profiles: dict[str, dict]     # {product_name: ProductProfile.model_dump()}

    # PM 在 Collector+Insight 完成后的评审台账，累加每一轮评审产出
    # status=forced 的项即报告中"未经充分审核"段落的数据源
    review_state: Annotated[list[dict], add]   # list[ReviewUnit.model_dump()]

    qa_results: list[dict]        # 终局 Doubao QA Agent 产出（与 PM inline QA 分离）
    report_status: Literal["pending", "passed", "unreviewed"]

    report_md: str | None
    report_pdf_path: str | None

    qa_notes: Annotated[list[str], add]
    audit_log: Annotated[list[dict], add]
