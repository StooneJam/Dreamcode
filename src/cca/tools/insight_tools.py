"""Insight Agent 专用工具 —— 模块级 @tool，供 create_react_agent 注册。

工具列表：
  scrape_app_store       — 爬取 App Store 评分与评论（Node.js 子进程）
  run_questionnaire      — 触发完整问卷 skill（设计→缓存→收集→脱敏）
  extract_topics         — NMF 主题提取
  analyze_sentiment_bert — BERT 三分类情感标注
  finalize_sentiment     — 提交 UserSentiment 结论到 state
  challenge_pm           — 向 PM 发出挑战信号（AgentSignal）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from cca.schema import AgentSignal, ChallengePayload, UserSentiment
from cca.settings import PROJECT_ROOT, load_config
from cca.skills.questionnaire.subgraph import run_questionnaire_skill
from cca.tools.appstore import scrape_app_store  # noqa: F401 — re-exported as agent tool
from cca.tools.nlp_utils import _bert_sentiment, _nmf_topics


def _effective_bert_model() -> str:
    """返回实际使用的 BERT 模型路径：优先微调后的本地模型，其次 config 指定值。"""
    cfg = load_config().get("nlp", {})
    ft_cfg = cfg.get("fine_tune", {})
    output_dir = PROJECT_ROOT / ft_cfg.get("model_output_dir", "data/models/bert_fine_tuned")
    if ft_cfg.get("enabled", False) and output_dir.exists():
        return str(output_dir)
    return cfg.get("bert_model", "lxyuan/distilbert-base-multilingual-cased-sentiments-student")


@tool
def run_questionnaire(product_name: str, competitor_names: str, dimensions: str) -> str:
    """为产品设计并收集用户问卷，返回问卷展示文本和回答 JSON。

    内部自动走缓存：同一产品名已有问卷时直接复用，不重复调 LLM。

    Args:
        competitor_names: 逗号分隔，如 "钉钉,企业微信"
        dimensions: 逗号分隔，如 "协同,定价,稳定性"
    """
    result = run_questionnaire_skill(
        product_name=product_name,
        competitor_names=[n.strip() for n in competitor_names.split(",") if n.strip()],
        dimensions=[d.strip() for d in dimensions.split(",") if d.strip()],
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def extract_topics(texts_json: str, n_topics: int = 5) -> str:
    """用 NMF 对文本列表做主题提取，返回主题关键词列表 JSON。

    Args:
        texts_json: JSON 数组字符串，每个元素为一条评论或回答文本。
    """
    texts = [t for t in json.loads(texts_json) if isinstance(t, str) and t.strip()]
    if not texts:
        return json.dumps([], ensure_ascii=False)
    return json.dumps(_nmf_topics(texts, n_topics), ensure_ascii=False)


@tool
def analyze_sentiment_bert(texts_json: str) -> str:
    """用 BERT 对文本列表做三分类情感标注，返回 {positive, negative, neutral} 分组 JSON。

    自动优先使用微调后的领域模型（若已训练），否则使用 config 指定的基础模型。
    分组后建议对每组单独调 extract_topics，得到正/负面维度的具体主题，可解释性强。

    Args:
        texts_json: JSON 数组字符串，每个元素为一条评论或回答文本。
    """
    model_name = _effective_bert_model()
    texts = [t for t in json.loads(texts_json) if isinstance(t, str) and t.strip()]
    return json.dumps(_bert_sentiment(texts, model_name), ensure_ascii=False)


@tool
def finalize_sentiment(product_name: str, sentiment_json: str) -> str:
    """提交产品的情感分析结论，写入 profiles.sentiment。

    Args:
        sentiment_json: 符合 UserSentiment schema 的 JSON 字符串。
          必填字段：positive_themes（list）、negative_themes（list）。
          appstore_cn_rating 若有则填入（ge=1, le=5），无则省略。
    """
    sentiment = UserSentiment.model_validate_json(sentiment_json)
    return json.dumps(
        {"product_name": product_name, "sentiment": sentiment.model_dump()},
        ensure_ascii=False,
    )


@tool
def challenge_pm(
    claim: str,
    evidence: list[str],
    suggested_fix: str | None = None,
    requires_debate: bool = False,
) -> str:
    """发现任务错误或数据矛盾时，向 PM 发出挑战信号。

    Args:
        claim: 挑战的核心陈述，一句话说清问题，如"产品名称有误，App Store 搜不到该应用"。
        evidence: 支撑 claim 的事实列表，至少 1 条，如搜索摘要或 App Store 返回的 error 字段。
        suggested_fix: 可选，建议的修正方向。
        requires_debate: 主观判断分歧时为 True；事实性错误（产品不存在等）为 False。
    """
    signal = AgentSignal(
        from_agent="insight",
        kind="pm_challenge",
        target="task_plan",
        payload=ChallengePayload(
            claim=claim,
            evidence=evidence,
            suggested_fix=suggested_fix,
        ),
        requires_debate=requires_debate,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()
