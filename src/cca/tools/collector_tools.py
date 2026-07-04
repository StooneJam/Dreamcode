"""Collector-specific @tools. Phase 1: finalize_exploration / challenge_pm;
phase 2: finalize_profile / request_product_replacement.

from_agent is hardcoded to "collector". ChallengePayload.evidence has min_length=1,
so zero evidence is rejected by Pydantic.
"""
from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.tools import tool

from cca.schema import (
    AgentSignal,
    ChallengePayload,
    CollectorExplorationResult,
    ProductProfile,
)
from cca.tools._validation import repair_llm_json, safe_load_validate


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _valid_evidence(ev: dict | None) -> bool:
    """Evidence needs at least a source_url, or Pydantic validation rejects it."""
    return isinstance(ev, dict) and bool(ev.get("source_url"))


def _clean_profile(raw: dict) -> dict:
    """Proactively clean common LLM schema deviations to raise the Pydantic validate pass rate.

    Cleaning rules (all other fields untouched):
    1. dimensions[].facts[].evidence[] drops entries missing source_url; a Fact whose evidence list becomes empty is dropped entirely
    2. after cleaning, a dimensions[] entry with empty facts is still kept (Pydantic allows it, though cross_product_note may not make sense)
    3. pricing.tiers[].source, if a dict missing source_url, is set to None
    4. sources[] drops entries missing source_url
    5. sentiment.sources[] cleaned the same way; sentiment.representative_reviews[].source handled like tier.source
    6. **automatically aggregates URLs from dimensions/pricing evidence into
       ProductProfile.sources** -- the LLM often skips the top-level sources field,
       so the tool backfills it to guarantee it's non-empty (doesn't rely on the LLM remembering)
    """
    for dim in raw.get("dimensions") or []:
        cleaned_facts = []
        for fact in dim.get("facts") or []:
            # the model puts the fact's body under all sorts of keys (Doubao has used
            # content/value/snippet...) when the schema wants statement. Rather than
            # maintain an alias whitelist (always missing one for the next product),
            # just take the longest string field other than evidence as the body --
            # the fact body is usually the longest, generalizes to any key, and
            # pairs with error-driven self-repair so nothing gets silently dropped.
            if not fact.get("statement"):
                cands = [v for k, v in fact.items() if k != "evidence" and isinstance(v, str) and v]
                if cands:
                    fact["statement"] = max(cands, key=len)
            ev_list = [ev for ev in (fact.get("evidence") or []) if _valid_evidence(ev)]
            if ev_list:
                fact["evidence"] = ev_list
                cleaned_facts.append(fact)
        dim["facts"] = cleaned_facts

    pricing = raw.get("pricing") or {}
    for tier in pricing.get("tiers") or []:
        if isinstance(tier.get("source"), dict) and not _valid_evidence(tier["source"]):
            tier["source"] = None

    raw["sources"] = [ev for ev in (raw.get("sources") or []) if _valid_evidence(ev)]

    sentiment = raw.get("sentiment")
    if isinstance(sentiment, dict):
        sentiment["sources"] = [ev for ev in (sentiment.get("sources") or []) if _valid_evidence(ev)]
        for rev in sentiment.get("representative_reviews") or []:
            if isinstance(rev.get("source"), dict) and not _valid_evidence(rev["source"]):
                rev["source"] = None

    _autofill_sources(raw)
    return raw


def _autofill_sources(raw: dict) -> None:
    """Aggregate URLs from dimensions.facts.evidence and pricing.tiers.source into raw['sources'].
    Dedupes + keeps whatever the LLM already filled in. Modifies raw in place."""
    existing_urls = {s["source_url"] for s in raw.get("sources") or [] if _valid_evidence(s)}
    new_sources: list[dict] = list(raw.get("sources") or [])

    def _try_add(ev: dict | None) -> None:
        if not _valid_evidence(ev):
            return
        url = ev["source_url"]
        if url in existing_urls:
            return
        existing_urls.add(url)
        # top-level sources doesn't duplicate the snippet (already in the dimension); keeps url + fetched_at
        entry: dict = {"source_url": url, "snippet": None}
        if fetched_at := ev.get("fetched_at"):
            entry["fetched_at"] = fetched_at  # otherwise Pydantic's default_factory=_now_iso covers it
        new_sources.append(entry)

    for dim in raw.get("dimensions") or []:
        for fact in dim.get("facts") or []:
            for ev in fact.get("evidence") or []:
                _try_add(ev)
    for tier in (raw.get("pricing") or {}).get("tiers") or []:
        _try_add(tier.get("source"))

    raw["sources"] = new_sources


@tool
def finalize_exploration(result_json: str) -> str:
    """Submit the round-one exploration conclusion, ending the ReAct loop. Must be called once after research is done.

    Args:
        result_json: JSON matching the CollectorExplorationResult schema. Fields:
            target_product / product_type (inferred online) / competitor_names (3-5) /
            discovered_dimensions / initial_profiles (with product_name / company /
            website / product_type); optional rationale explaining the choices --
            **if fetch_url failed, explain the pivot reason here**.
    """
    obj, err = safe_load_validate(result_json, CollectorExplorationResult)
    if err:
        return err
    return obj.model_dump_json()


@tool
def challenge_pm(
    claim: str,
    evidence: list[str],
    suggested_fix: str | None = None,
    requires_debate: bool = False,
) -> str:
    """Challenge PM's InitialBrief.

    Pass requires_debate=False for factual errors (wrong company_hint / product
    discontinued); True for subjective disagreements (target_product's
    reasonableness). evidence needs at least 1 entry.
    """
    signal = AgentSignal(
        from_agent="collector", kind="pm_challenge", target="initial_brief",
        payload=ChallengePayload(claim=claim, evidence=evidence, suggested_fix=suggested_fix),
        requires_debate=requires_debate, ts=_now(),
    )
    return signal.model_dump_json()


def _submit_receipt(profile: ProductProfile) -> tuple[str, dict]:
    """Build finalize_profile's return: the model only sees content (success + stop
    instruction); the profile travels through the artifact side-channel.

    content only shows the model a stop instruction; the profile comes back via
    artifact, which collect_one_product uses to persist it.
    """
    content = (
        f"提交成功：{profile.product_name} ProductProfile 已入库"
        f"（{len(profile.dimensions)} 个维度，{len(profile.sources)} 个来源）。"
        f"本产品 ReAct 任务已完成，请立即停止所有工具调用，"
        f"不得再次调用 finalize_profile。"
    )
    return content, {"profile": profile.model_dump()}


@tool(response_format="content_and_artifact")
def finalize_profile(product_name: str, profile_json: str) -> tuple[str, dict]:
    """Submit a single product's ProductProfile, ending this product's ReAct loop.
    Must be called once after every CollectTask is done.

    Fields Collector should fill: product_name / product_type / target_users /
    website / dimensions (each Dimension.facts needs each Fact.evidence with
    min_length=1, each Evidence an object with source_url, not a bare URL string) /
    pricing (tiers[].source likewise an object with source_url) / sources.
    **Don't** fill sentiment (Insight owns that).

    The tool proactively normalizes common mistakes (a bare URL string / {url:...}
    auto-fills to {source_url:...}; only an Evidence truly missing source_url gets
    dropped; only a Fact truly missing evidence gets dropped). If it's still invalid
    after cleanup, an error string with the field path is returned for ReAct to self-correct.
    """
    def _clean(d: dict) -> dict:
        # first normalize a bare URL / {url} -> {source_url} (Doubao's frequent mistake), then run the existing cleanup
        d = repair_llm_json(d)
        # overwrite with the outer parameter regardless of whether the model passed
        # product_name, to avoid a Field-required loop
        d = _clean_profile(d)
        d["product_name"] = product_name
        return d

    profile, err = safe_load_validate(
        profile_json, ProductProfile,
        pre_clean=_clean,
        hint=(
            "字段规则提示："
            "\n- Dimension 必填：name, facts（category 可选）"
            "\n- Fact 必填：statement, evidence（list 非空）"
            "\n- Evidence 必填：source_url"
            "\n- PricingInfo.pricing_model 用 per_user/per_team/custom/unknown（其他值自动归 unknown）"
        ),
    )
    if not err:
        return _submit_receipt(profile)
    # after relaxing the schema, failures are almost always a type error or
    # unrecoverable truncation: return the error for the model to self-correct
    # (fields are no longer silently stripped)
    return err, {"profile": None}


@tool
def request_product_replacement(
    product_name: str,
    reason: str,
    evidence: list[str],
) -> str:
    """When a CollectTask's product is completely uncollectable, request a
    replacement from PM (a factual data_gap signal).

    Applies to: not findable online / official site 404s / delisted from the store /
    fetch quota exhausted. Subjective "doesn't feel like it qualifies" doesn't belong
    here -- that's phase 1's challenge_pm.
    """
    signal = AgentSignal(
        from_agent="collector", kind="data_gap", target="task_plan",
        payload=ChallengePayload(
            claim=f"产品『{product_name}』数据无法采集：{reason}",
            evidence=evidence,
            suggested_fix=f"从竞品列表移除 {product_name}，可由 PM 选替代品",
        ),
        requires_debate=False, ts=_now(),
    )
    return signal.model_dump_json()
