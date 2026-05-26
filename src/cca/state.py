"""
LangGraph 主图共享状态。
与 Pydantic 领域模型分文件：domain 类在 schema.py，运行时状态在这里。
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


def _merge_profiles(left: dict[str, dict], right: dict[str, dict]) -> dict[str, dict]:
    """profiles 的 merge reducer：同 key 时右侧字段覆盖左侧，保留双方独有字段。

    Collector 写 dimensions/pricing/sources，Insight 写 sentiment，Analyst 写 swot。
    并发写入时各自只更新自己的字段，不丢弃对方已写的字段。
    """
    merged = dict(left)
    for name, profile in right.items():
        if name in merged:
            merged[name] = {**merged[name], **profile}
        else:
            merged[name] = profile
    return merged


class CCAState(TypedDict):
    """Agent 间共享的工作台。

    profiles 以 product_name 为 key 存 ProductProfile.model_dump()；
    review_state / audit_log / qa_notes 用 add reducer，多节点并发写入自动追加。
    """
    user_query: str
    target_product: str

    # 用户上传文档路径（CLI/Streamlit 在调用 graph 前写入），第一版只取第一个
    # PM phase 1 直接消化这些文件。
    user_files: list[str] | None

    # PM 阶段一 InitialBrief；Collector 一轮 ExplorationResult（debate 收敛后写回）
    initial_brief: dict | None           # InitialBrief.model_dump()
    # PM phase 1 蒸馏用户文档产出的领域 hint（仅当 user_files 非空时填）；
    # 下游 Collector / Insight / Analyst 共享
    domain_seed: dict | None             # DomainSeed.model_dump()
    exploration_result: dict | None      # CollectorExplorationResult.model_dump()

    # PM 阶段二~四下发的任务
    competitor_names: list[str]
    task_plan: dict | None               # TaskPlan.model_dump() - PM 阶段二填
    analyst_task: dict | None            # AnalystTask.model_dump() - PM 阶段三填
    report_task: dict | None             # ReportTask.model_dump() - PM 阶段四填

    # 各产品档案（Collector / Insight / Analyst / PM 逐层填充）
    # _merge_profiles reducer：并发写入时各 Agent 只覆盖自己的字段，不清除其他 Agent 已写字段
    profiles: Annotated[dict[str, dict], _merge_profiles]

    # PM 评审台账，累加每一轮评审产出
    # status=forced 的项即报告中"未经充分审核"段落的数据源
    review_state: Annotated[list[dict], add]   # list[ReviewUnit.model_dump()]

    # 报告终审产出（来自 call_report_reviewer skill 的跨家族 debate）
    qa_results: list[dict]
    report_status: Literal["pending", "passed", "failed", "unreviewed"]
    report_md: str | None
    report_pdf_path: str | None

    # 跨阶段累加的日志与信号
    qa_notes: Annotated[list[str], add]
    audit_log: Annotated[list[dict], add]
    debate_results: Annotated[list[dict], add]   # DebateResult.model_dump() 累加
    agent_signals: Annotated[list[dict], add]    # AgentSignal.model_dump() 累加（永不删，供回溯审计）
    consumed_signal_ids: Annotated[list[str], add]  # PM 已处理的 signal_id，去重指针
    decision_log: Annotated[list[dict], add]     # DecisionRecord.model_dump() 累加，支撑离线 Q&A 与 debate defense
