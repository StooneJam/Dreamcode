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

    # PM 阶段一 InitialBrief；Collector 一轮 ExplorationResult（debate 收敛后写回）
    initial_brief: dict | None           # InitialBrief.model_dump()
    exploration_result: dict | None      # CollectorExplorationResult.model_dump()

    # PM 阶段二~四下发的任务
    competitor_names: list[str]
    task_plan: dict | None               # TaskPlan.model_dump() - PM 阶段二填
    analyst_task: dict | None            # AnalystTask.model_dump() - PM 阶段三填
    report_task: dict | None             # ReportTask.model_dump() - PM 阶段四填

    # 各产品档案（Collector / Insight / Analyst / PM 逐层填充）
    profiles: dict[str, dict]     # {product_name: ProductProfile.model_dump()}

    # PM 评审台账，累加每一轮评审产出
    # status=forced 的项即报告中"未经充分审核"段落的数据源
    review_state: Annotated[list[dict], add]   # list[ReviewUnit.model_dump()]

    # 报告终审产出（来自 call_report_reviewer skill 的跨家族 debate）
    qa_results: list[dict]
    report_status: Literal["pending", "passed", "unreviewed"]
    report_md: str | None
    report_pdf_path: str | None

    # 跨阶段累加的日志与信号
    qa_notes: Annotated[list[str], add]
    audit_log: Annotated[list[dict], add]
    debate_results: Annotated[list[dict], add]   # DebateResult.model_dump() 累加
    agent_signals: Annotated[list[dict], add]    # AgentSignal.model_dump() 累加
