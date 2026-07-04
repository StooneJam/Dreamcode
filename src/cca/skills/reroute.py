"""reroute skill -- root-cause analysis + phase rollback for factual signals.

The symmetric counterpart to debate: triggered when AgentSignal.requires_debate=false.
"""
from __future__ import annotations

import json
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from cca.llm.factory import get_llm
from cca.schema import AgentSignal

RerouteTarget = str  # "phase_1" | "phase_2" | "phase_3"

_PHASE_FIELD = {
    "phase_1": "exploration_result",
    "phase_2": "task_plan",
    "phase_3": "report_task",
}

_SYSTEM_PROMPT = """You are the "reroute" correction skill in a competitive analysis system.
A downstream agent has reported a factual problem (missing data / dead URL / bad data,
etc.) -- not a subjective judgment call. Your job: diagnose the root cause and decide
which phase to roll back to.

## Semantics of the three phases
- phase_1 (collection layer): Collector fetches raw data online. Rolling back here clears exploration_result.
- phase_2 (planning layer): PM builds a TaskPlan from existing collection results. Rolling back here doesn't re-collect, just re-plans tasks.
- phase_3 (report layer): PM hands Reporter a ReportTask (focus_dimensions / sections /
  SWOT scope). Roll back here when collection+sentiment data is fine but the report
  task itself is unreasonable.

## Decision rules
- single-product data missing / dead URL / wrong data scraped -> phase_2
  (PM re-plans task_plan adding the missing dimension then fans out a re-collect,
  without redoing exploration, to preserve the debate-converged competitor_names)
- fake/discontinued product -> phase_1
  (exploration itself was wrong, must redo the rough exploration)
- exploration_result is broadly unusable -> phase_1
- collected data is correct but competitor_names / priority_dimensions / task
  allocation is wrong -> phase_2
- ReviewUnit passed but ReportTask's focus_dimensions / sections have insufficient data -> phase_3
- a section goes beyond the data's scope, or SWOT covers a product outside profiles -> phase_3
- default preference is phase_2 re-collection, to avoid redoing exploration and
  losing already-converged information
"""


class RerouteDecision(BaseModel):
    """reroute's output: root-cause diagnosis + a rollback instruction."""

    target_phase: RerouteTarget = Field(
        description="Rollback phase: phase_1 / phase_2 / phase_3; see the decision rules in the system prompt"
    )
    root_cause: str = Field(description="Root-cause analysis, one sentence")
    fix_summary: dict = Field(
        description="Fix suggestions, key=field name to change, value=the fix's content or direction"
    )
    rationale: str = Field(description="Why roll back to this phase and not another")


def reroute(signal: AgentSignal, state_json: str) -> RerouteDecision:
    """Analyze a factual signal and produce a rollback decision. state_json is a minimal state slice snapshot."""
    # method="function_calling" is explicit to bypass langchain-openai 0.3+'s default json_schema strict mode.
    # Strict mode requires dict fields to explicitly set additionalProperties=false;
    # RerouteDecision.fix_summary is a bare dict and gets rejected (400 BadRequest) by
    # strict mode. Same pattern as pm._invoke_pm.
    llm = get_llm("gpt-5").with_structured_output(RerouteDecision, method="function_calling")
    user = json.dumps({"signal": signal.model_dump(), "state": state_json}, ensure_ascii=False)
    return cast(
        RerouteDecision,
        llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user)]),
    )


def apply_reroute(decision: RerouteDecision) -> dict:
    """reroute decision -> state update dict."""
    updates: dict = {}
    if field := _PHASE_FIELD.get(decision.target_phase):
        updates[field] = None
    updates["audit_log"] = [{"agent": "reroute", "decision": decision.model_dump()}]
    return updates


def apply_reroute_phase(target_phase: RerouteTarget) -> dict:
    """Produce the state update directly when the target phase is already known, skipping the LLM diagnosis.

    review_node's precheck-produced data_gap always has phase_2 as its root cause,
    so there's no need to call the reroute LLM again.
    """
    updates: dict = {}
    if field := _PHASE_FIELD.get(target_phase):
        updates[field] = None
    updates["audit_log"] = [{
        "agent": "reroute", "auto_phase": target_phase,
        "note": "已知根因，跳过 LLM 诊断",
    }]
    return updates
