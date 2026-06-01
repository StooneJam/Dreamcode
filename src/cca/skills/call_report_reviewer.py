"""call_report_reviewer skill — Doubao 跨家族审查报告 MD 与 profiles 的一致性。"""
from __future__ import annotations

import json
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import get_llm
from cca.schema import QAResult


class _ReviewOutput(BaseModel):
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    note: str | None = None


_SYSTEM = """\
你是竞品分析报告的质检专家。核查报告内容是否忠实于原始档案数据，识别无法溯源的事实断言。

检查清单：
1. 报告中的所有产品名、公司名是否出现在档案数据中
2. 数值数据（定价、评分、用户数等）是否与档案一致，不得自行推算或估值
3. 结论段落是否存在超出档案范围的无依据断言（合理归纳允许，无来源断言不允许）
4. 标注为低置信度的数据是否已在报告中注明

判定标准：
- passed=true：无重大错误或仅有轻微措辞差异
- passed=false：存在 1 条以上无法溯源的事实性断言
- retry_recommended=true：存在影响结论可信度的重大错误
- failed_checks：每条问题格式为"[章节名] 具体问题描述"\
"""


def call_report_reviewer(report_md: str, profiles: dict[str, dict]) -> QAResult:
    """Doubao 跨家族审查报告一致性与事实可溯源性。"""
    profiles_json = json.dumps(profiles, ensure_ascii=False, indent=2)
    user = (
        f"## 原始档案数据（Ground Truth）\n\n```json\n{profiles_json}\n```\n\n"
        f"## 待审查报告\n\n{report_md}"
    )
    llm = get_llm("doubao").with_structured_output(_ReviewOutput, method="function_calling")
    out = cast(
        _ReviewOutput,
        llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)]),
    )
    return QAResult(
        product_name="__report__",
        passed=out.passed,
        failed_checks=out.failed_checks,
        retry_recommended=out.retry_recommended,
        note=out.note,
    )
