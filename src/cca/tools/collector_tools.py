"""Collector 专用 @tool。phase 1：finalize_exploration / challenge_pm；
phase 2：finalize_profile / request_product_replacement。

from_agent 硬编码为 "collector"。ChallengePayload.evidence min_length=1，零证据会被 Pydantic 拒。
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
from cca.tools._validation import safe_load_validate


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
            # 模型把事实正文放在五花八门的 key（实测豆包用过 content/value/snippet…），schema 要
            # statement。不维护别名白名单（换产品永远漏下一个）；直接取除 evidence 外最长的字符串
            # 当正文——事实正文通常最长，泛化到任意 key，配合返错自愈彻底不 husk。
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


def _submit_receipt(profile: ProductProfile) -> tuple[str, dict]:
    """构造 finalize_profile 返回：模型只看到 content（成功+停止），profile 走 artifact 暗channel。

    content 只给模型看停止指令；profile 经 artifact 回传，collect_one_product 据此入库。
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
            "\n- Dimension 必填：name, facts（category 可选）"
            "\n- Fact 必填：statement, evidence（list 非空）"
            "\n- Evidence 必填：source_url"
            "\n- PricingInfo.pricing_model 用 per_user/per_team/custom/unknown（其他值自动归 unknown）"
        ),
    )
    if not err:
        return _submit_receipt(profile)
    # 放松后 schema 几乎只在类型错 / 截断不可救时失败：返错让模型自修重试（不再静默剥字段）
    return err, {"profile": None}


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
