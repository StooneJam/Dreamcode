"""Collector 专用 @tool。phase 1：finalize_exploration / challenge_pm；
phase 2：finalize_profile / request_product_replacement。

from_agent 硬编码为 "collector"。ChallengePayload.evidence min_length=1，零证据会被 Pydantic 拒。
"""
from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.tools import tool
from pydantic import ValidationError

from cca.schema import (
    AgentSignal,
    ChallengePayload,
    CollectorExplorationResult,
    ProductProfile,
)
from cca.tools._validation import _try_parse_lenient, safe_load_validate


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _valid_evidence(ev: dict | None) -> bool:
    """Evidence 至少要有 source_url，否则 Pydantic 校验会拒。"""
    return isinstance(ev, dict) and bool(ev.get("source_url"))


def _clean_profile(raw: dict) -> dict:
    """主动清洗 LLM 常见 schema 偏差，让 Pydantic validate 通过率更高。

    清洗规则（保持其余字段不动）：
    1. dimensions[].facts[].evidence[] 删除缺 source_url 的项；evidence 列表清空后整条 Fact 删除
    2. dimensions[] 清完后若 facts 为空也保留（Pydantic 允许，但 cross_product_note 可能没意义）
    3. pricing.tiers[].source 若 dict 且缺 source_url → 置 None
    4. sources[] 删除缺 source_url 的项
    5. sentiment.sources[] 同样清洗；sentiment.representative_reviews[].source 同 tier.source 处理
    6. **自动从 dimensions/pricing 的 evidence 聚合 URL 补到 ProductProfile.sources** ——
       LLM 经常漏填顶层 sources，工具兜底确保不为空（不依赖 LLM 自觉）。
    """
    for dim in raw.get("dimensions") or []:
        cleaned_facts = []
        for fact in dim.get("facts") or []:
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
    """从 dimensions.facts.evidence 和 pricing.tiers.source 聚合 URL 到 raw['sources']。
    去重 + 保留 LLM 已填的项。原地修改 raw。"""
    existing_urls = {s["source_url"] for s in raw.get("sources") or [] if _valid_evidence(s)}
    new_sources: list[dict] = list(raw.get("sources") or [])

    def _try_add(ev: dict | None) -> None:
        if not _valid_evidence(ev):
            return
        url = ev["source_url"]
        if url in existing_urls:
            return
        existing_urls.add(url)
        # 顶层 sources 不重复存 snippet（dimension 内已经带了），保留 url + fetched_at
        entry: dict = {"source_url": url, "snippet": None}
        if fetched_at := ev.get("fetched_at"):
            entry["fetched_at"] = fetched_at  # 否则 Pydantic default_factory=_now_iso 兜底
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
    """提交一轮探索结论，结束 ReAct 循环。完成调研后**必须调用一次**。

    Args:
        result_json: 符合 CollectorExplorationResult schema 的 JSON。字段：
            target_product / product_type（联网推断）/ competitor_names（3-5 家）/
            discovered_dimensions / initial_profiles（含 product_name / company / website / product_type）；
            可选 rationale，说明选择依据；**fetch_url 失败时务必在此说明换向原因**。
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
    """挑战 PM 的 InitialBrief。

    事实性错误（company_hint 错 / 产品停服）传 requires_debate=False；
    主观分歧（target_product 合理性）传 True。evidence 至少 1 条。
    """
    signal = AgentSignal(
        from_agent="collector", kind="pm_challenge", target="initial_brief",
        payload=ChallengePayload(claim=claim, evidence=evidence, suggested_fix=suggested_fix),
        requires_debate=requires_debate, ts=_now(),
    )
    return signal.model_dump_json()


# 校验失败时可整体剥离的顶层字段（嵌套大 / 枚举严格，模型重试也难修对）。
# product_type/target_users/website 等标量不在此列：模型一次重试即可改对，不该静默丢。
_DROPPABLE_FIELDS = {"dimensions", "pricing", "sources"}


def _strip_to_valid(base: dict) -> tuple[ProductProfile, list[str]] | None:
    """逐次删除 Pydantic 实际报错的顶层字段直到验过，只丢坏字段、保住其余数据。

    与旧版"累加式 + dimensions 优先"不同：pricing 出错只删 pricing，不连累好 dimensions。
    错误落在不可删字段（如必填 product_name）上时无法补救，返 None 让模型重试。
    """
    trial = dict(base)
    dropped: list[str] = []
    while True:
        try:
            return ProductProfile.model_validate(trial), dropped
        except ValidationError as exc:
            bad = {
                str(e["loc"][0]) for e in exc.errors()
                if e["loc"] and str(e["loc"][0]) in _DROPPABLE_FIELDS
            } - set(dropped)
            if not bad:
                return None
            for field in bad:
                trial.pop(field, None)
                dropped.append(field)


def _submit_receipt(profile: ProductProfile, dropped: list[str]) -> tuple[str, dict]:
    """构造 finalize_profile 返回：模型只看到 content（成功+停止），profile 走 artifact 暗channel。

    剥离过字段时 content 注明、artifact.degraded 携带字段名，collect_one_product 据此标 forced。
    """
    note = f"，已剥离无法校验字段 {dropped}（数据不完整）" if dropped else ""
    content = (
        f"提交成功：{profile.product_name} ProductProfile 已入库"
        f"（{len(profile.dimensions)} 个维度，{len(profile.sources)} 个来源{note}）。"
        f"本产品 ReAct 任务已完成，请立即停止所有工具调用，"
        f"不得再次调用 finalize_profile。"
    )
    return content, {"profile": profile.model_dump(), "degraded": dropped}


@tool(response_format="content_and_artifact")
def finalize_profile(product_name: str, profile_json: str) -> tuple[str, dict]:
    """提交单产品 ProductProfile，结束当前产品 ReAct 循环。每个 CollectTask 完成后**必须调用一次**。

    Collector 该填字段：product_name / product_type / target_users / website /
    dimensions（每个 Dimension.facts 每条 Fact.evidence min_length=1，每条 Evidence 必填 source_url）/
    pricing / sources。**不要**填 sentiment（Insight owner）。

    工具会主动清洗常见 schema 偏差（无 source_url 的 Evidence 会被剔除；无证据的 Fact 会被剔除）。
    清洗后仍不合规会返回错误字符串带具体字段路径，ReAct 看到后修 JSON 重试。
    """
    def _clean(d: dict) -> dict:
        # 无论模型是否传入 product_name，都用外层参数覆盖，避免 Field required 循环
        d = _clean_profile(d)
        d["product_name"] = product_name
        return d

    profile, err = safe_load_validate(
        profile_json, ProductProfile,
        pre_clean=_clean,
        hint=(
            "字段规则提示："
            "\n- Dimension 必填：name, category, facts"
            "\n- Fact 必填：statement, evidence（list 非空）"
            "\n- Evidence 必填：source_url"
            "\n- PricingInfo 必填：has_free_tier (bool), pricing_model (per_user/per_team/custom/unknown)"
        ),
    )
    if not err:
        return _submit_receipt(profile, [])

    # 校验失败：精准剥离报错字段后提交，避免模型对不可修复错误（Doubao 截断等）无限重试
    partial_raw, _ = _try_parse_lenient(profile_json)
    if isinstance(partial_raw, dict):
        stripped = _strip_to_valid(_clean(partial_raw))
        if stripped is not None:
            return _submit_receipt(*stripped)
    return err, {"profile": None, "degraded": None}  # 无法补救才返错让模型重试


@tool
def request_product_replacement(
    product_name: str,
    reason: str,
    evidence: list[str],
) -> str:
    """CollectTask 指定的产品完全无法采集时，向 PM 申请换产品（事实性 data_gap 信号）。

    适用：联网搜不到 / 官网 404 / 商店下架 / fetch 配额耗尽。
    主观"觉得不够格"不在此——那是 phase 1 challenge_pm 的事。
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
