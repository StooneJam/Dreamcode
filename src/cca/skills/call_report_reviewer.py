"""call_report_reviewer skill — Reporter 调用 Doubao 跨家族审查报告 MD。

D-017 落档：v1 占位，真正实现待 5.31 联调阶段接入 Doubao 多模态。
"""
from __future__ import annotations

from cca.schema import QAResult


def call_report_reviewer(report_md: str, profiles: dict[str, dict]) -> QAResult:
    """Doubao 跨家族审查报告一致性。

    真实现要：
    1. 把 report_md + profiles 喂给 Doubao 多模态模型
    2. 检查图文一致 / 事实可溯 / 无幻觉
    3. 输出 QAResult，由 Reporter 决定是否重写

    v1 占位：返回固定 pass，不真审查。
    """
    return QAResult(
        product_name="__report__",
        passed=True,
        failed_checks=[],
        retry_recommended=False,
        note="v1 占位：call_report_reviewer 未真接入 Doubao，待 5.31 联调阶段补",
    )
