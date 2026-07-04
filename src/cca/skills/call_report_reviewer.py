"""call_report_reviewer skill -- Doubao cross-family review of report MD vs. profiles consistency."""
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
You are a QA expert for competitive analysis reports. Check whether the report content
is faithful to the original profile data, and identify any factual claims that can't be traced back to it.

Checklist:
1. Do all product names and company names in the report appear in the profile data?
2. Do numeric figures (pricing, ratings, user counts, etc.) match the profile data, with no self-computed or estimated values?
3. Does the conclusion section make any unsupported claims beyond the profile data (reasonable synthesis is fine, unsourced claims are not)?
4. Is data flagged as low-confidence noted as such in the report?

Verdict criteria:
- passed=true: no major errors, or only minor wording differences
- passed=false: one or more untraceable factual claims exist
- retry_recommended=true: an error exists that materially affects the conclusion's credibility
- failed_checks: each item formatted as "[section name] specific description of the issue"\
"""


def call_report_reviewer(report_md: str, profiles: dict[str, dict]) -> QAResult:
    """Doubao cross-family review of report consistency and factual traceability."""
    profiles_json = json.dumps(profiles, ensure_ascii=False, indent=2)
    user = (
        f"## Original Profile Data (Ground Truth)\n\n```json\n{profiles_json}\n```\n\n"
        f"## Report Under Review\n\n{report_md}"
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
