"""NLP 工具函数 —— NMF 主题提取 + BERT 情感分类。

设计原则：
- sklearn / transformers 均延迟 import，避免未安装时 import 报错
- BERT pipeline 进程内单例缓存，同一 model_name 只加载一次（约 250 MB）
- 支持领域微调模型：nlp.bert_model 指向本地路径时自动使用微调版
"""
from __future__ import annotations

# BERT pipeline 单例缓存：model_name → pipeline 实例
_bert_pipeline_cache: dict[str, object] = {}


def _nmf_topics(texts: list[str], n_topics: int = 5) -> list[str]:
    """NMF 主题提取，短文本（评论 / 问卷）场景优于 LDA。

    返回每个主题的 top-5 关键词，格式如 "协同 / 消息 / 通知"。
    """
    if not texts:
        return []

    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    n_topics = min(n_topics, max(1, len(texts)))
    vectorizer = TfidfVectorizer(max_features=300, min_df=1)
    tfidf = vectorizer.fit_transform(texts)
    model = NMF(n_components=n_topics, random_state=42, max_iter=300)
    model.fit(tfidf)
    names = vectorizer.get_feature_names_out()
    return [
        " / ".join(names[i] for i in topic.argsort()[-5:][::-1])
        for topic in model.components_
    ]


def _bert_sentiment(texts: list[str], model_name: str) -> dict[str, list[str]]:
    """BERT 三分类情感标注，返回 {positive, negative, neutral} 分组。

    支持本地微调模型路径（领域适配后效果更好）。
    pipeline 进程内缓存，同一 model_name 只加载一次。
    未知标签统一归入 neutral。
    """
    if not texts:
        return {"positive": [], "negative": [], "neutral": []}

    if model_name not in _bert_pipeline_cache:
        from transformers import pipeline
        _bert_pipeline_cache[model_name] = pipeline(
            "text-classification", model=model_name, top_k=1
        )

    classifier = _bert_pipeline_cache[model_name]
    groups: dict[str, list[str]] = {"positive": [], "negative": [], "neutral": []}
    results = classifier(texts, truncation=True, max_length=512)
    for text, res in zip(texts, results):
        label = res[0]["label"].lower()
        groups.get(label, groups["neutral"]).append(text)
    return groups
