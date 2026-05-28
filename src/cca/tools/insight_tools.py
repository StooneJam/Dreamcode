"""Insight 专用 @tool：问卷 / NMF / BERT / finalize_sentiment / challenge_pm。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from cca.schema import AgentSignal, ChallengePayload, UserSentiment
from cca.settings import PROJECT_ROOT, load_config
from cca.skills.questionnaire.subgraph import run_questionnaire_skill
from cca.tools._validation import safe_load_validate
from cca.tools.appstore import scrape_app_store  # noqa: F401 — re-exported as agent tool
from cca.utils.nlp_utils import _bert_sentiment, _nmf_topics


def _safe_text_list(texts_json: str) -> tuple[list[str] | None, str | None]:
    """parse JSON 文本数组 → 过滤掉空/非字符串。"""
    try:
        raw = json.loads(texts_json)
    except json.JSONDecodeError as e:
        return None, (
            f"texts_json 不是合法 JSON：{e.msg}（line {e.lineno} col {e.colno}）。"
            f"应为字符串数组形如 [\"评论1\", \"评论2\"]。"
        )
    if not isinstance(raw, list):
        return None, f"texts_json 必须是 JSON 数组，实际为 {type(raw).__name__}。"
    return [t for t in raw if isinstance(t, str) and t.strip()], None


def _effective_bert_model() -> str:
    """优先返回本地微调模型路径；否则回退 config.nlp.bert_model。"""
    cfg = load_config().get("nlp", {})
    ft = cfg.get("fine_tune", {})
    output = PROJECT_ROOT / ft.get("model_output_dir", "data/models/bert_fine_tuned")
    if ft.get("enabled", False) and output.exists():
        return str(output)
    return cfg.get("bert_model", "lxyuan/distilbert-base-multilingual-cased-sentiments-student")


@tool
def run_questionnaire(product_name: str, competitor_names: str, dimensions: str) -> str:
    """设计并收集用户问卷（含 SQLite 缓存）。

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
    """NMF 主题提取。texts_json 是文本数组 JSON；返回主题关键词列表 JSON。"""
    texts, err = _safe_text_list(texts_json)
    if err:
        return err
    if not texts:
        return json.dumps([], ensure_ascii=False)
    return json.dumps(_nmf_topics(texts, n_topics), ensure_ascii=False)


@tool
def analyze_sentiment_bert(texts_json: str) -> str:
    """BERT 三分类情感。优先用本地微调模型，否则 config 指定的基础模型。

    返回 {positive: [...], negative: [...], neutral: [...]}；建议各组单独再调 extract_topics。
    """
    texts, err = _safe_text_list(texts_json)
    if err:
        return err
    try:
        return json.dumps(_bert_sentiment(texts, _effective_bert_model()), ensure_ascii=False)
    except ImportError as e:
        # D-035 工具失败协议：永不向 ToolNode raise，返 LLM-friendly 错误让 LLM fallback。
        return (
            f"BERT 情感分析工具不可用（{e}）。"
            f"请改用 web_search + LLM 推理判断情感，直接调用 finalize_sentiment 提交结论；"
            f"positive_themes / negative_themes 由你基于评论文本自行总结。"
        )
    except Exception as e:
        return (
            f"BERT 情感分析运行时错误：{type(e).__name__}: {e}。"
            f"请改用 LLM 推理判断情感后直接调用 finalize_sentiment。"
        )


@tool
def finalize_sentiment(product_name: str, sentiment_json: str) -> str:
    """提交单产品 UserSentiment。必填 positive_themes / negative_themes；
    appstore_cn_rating 有则填（1–5）。"""
    sentiment, err = safe_load_validate(
        sentiment_json, UserSentiment,
        hint=(
            "字段规则提示："
            "\n- positive_themes / negative_themes 必填字符串数组"
            "\n- appstore_cn_rating 可选，浮点 1.0–5.0"
            "\n- representative_reviews[].rating 可选，整数 1–5"
            "\n- platform 枚举: appstore_cn / appstore_us / zhihu / weibo / other"
        ),
    )
    if err:
        return err
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
    """挑战 PM 的 TaskPlan。事实性错误（产品不存在等）传 requires_debate=False，
    主观分歧（受众/维度异议）传 True。evidence 至少 1 条。"""
    signal = AgentSignal(
        from_agent="insight", kind="pm_challenge", target="task_plan",
        payload=ChallengePayload(claim=claim, evidence=evidence, suggested_fix=suggested_fix),
        requires_debate=requires_debate,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    return signal.model_dump_json()
