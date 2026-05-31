"""NLP 工具函数 —— BERT 情感分类。

设计原则：
- transformers 延迟 import，避免未安装时 import 报错
- BERT pipeline 进程内单例缓存，同一 model_name 只加载一次（约 250 MB）
- 支持领域微调模型：nlp.bert_model 指向本地路径时自动使用微调版
"""
from __future__ import annotations

# BERT pipeline 单例缓存：model_name → pipeline 实例
_bert_pipeline_cache: dict[str, object] = {}


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
