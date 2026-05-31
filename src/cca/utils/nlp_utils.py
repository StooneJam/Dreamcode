"""NLP 工具函数 —— NMF 主题提取 + BERT 情感分类。

设计原则：
- sklearn / transformers 均延迟 import，避免未安装时 import 报错
- BERT pipeline 进程内单例缓存，同一 model_name 只加载一次（约 250 MB）
- 支持领域微调模型：nlp.bert_model 指向本地路径时自动使用微调版
"""
from __future__ import annotations

# BERT pipeline 单例缓存：model_name → pipeline 实例
_bert_pipeline_cache: dict[str, object] = {}

# NMF 预处理停用词：中文功能词 + 业务泛词 + 英文停用词。
# 目的——把"业务无关词汇"挡在词表外，否则 NMF 主题会被 的/了/the/产品 这类高频无信息词占满。
# 注意：只放无区分度的泛词，绝不放 协同/视频/定价 这类真正的竞品维度词。
_STOPWORDS: frozenset[str] = frozenset({
    # 中文功能词
    "的", "了", "是", "在", "和", "也", "都", "就", "很", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "这", "那", "这个", "那个", "这些", "那些", "有", "没", "没有",
    "不", "要", "会", "能", "可以", "把", "被", "给", "让", "跟", "与", "及", "或", "但",
    "而", "并", "还", "又", "再", "就是", "还是", "因为", "所以", "但是", "如果", "虽然",
    "然后", "以及", "什么", "怎么", "这样", "那样", "一个", "一些", "一下", "非常", "真的",
    "觉得", "感觉", "比较", "起来", "出来", "时候", "目前", "现在", "已经", "通过", "进行",
    "对于", "关于",
    # 业务无关泛词（每条评论都有、无区分度）
    "产品", "软件", "应用", "公司", "企业", "用户", "团队", "工作", "工具", "平台",
    "使用", "方面", "情况", "东西", "方式", "内容", "支持", "提供", "需要", "整体", "功能",
    # 英文停用词
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "for", "with", "that", "this", "it", "its", "as", "by", "at",
    "from", "has", "have", "had", "will", "would", "can", "could", "should", "not", "no",
    "so", "do", "does", "did", "you", "your", "i", "we", "they", "he", "she", "app", "very",
    "really", "just", "some", "there", "their", "my", "me", "if", "than", "then", "also", "get",
})


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 过滤：单字 / 停用词 / 纯数字 / 纯标点一律剔除。

    中文无空格，必须先分词；英文已是词，jieba 会原样切出。两者共用同一停用词过滤。
    """
    import jieba

    out: list[str] = []
    for token in jieba.cut(text):
        token = token.strip()
        if len(token) < 2 or token in _STOPWORDS or token.isdigit():
            continue
        if not any(ch.isalnum() for ch in token):  # 纯标点 / 符号
            continue
        out.append(token)
    return out


def _build_tfidf(texts: list[str]):
    """jieba 分词 + 停用词过滤构 TF-IDF 矩阵。空词表（全被过滤）返回 (None, None)。"""
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(
        tokenizer=_tokenize, token_pattern=None,
        lowercase=True, max_features=300, min_df=1,
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return None, None
    if matrix.shape[1] == 0:
        return None, None
    return vectorizer, matrix


def _nmf_topics(texts: list[str], n_topics: int = 5) -> list[str]:
    """NMF 主题提取，短文本（评论 / 问卷）场景优于 LDA。

    预处理见 _build_tfidf。返回每个主题的 top-3 关键词，格式如 "协同 / 消息 / 通知"
    （少而精，给报告正文 themes 用；词云的多词另由 _topic_word_freq 取 TF-IDF top-N）。
    全是停用词导致空词表时返 []，不抛。
    """
    if not texts:
        return []

    from sklearn.decomposition import NMF

    vectorizer, tfidf = _build_tfidf(texts)
    if tfidf is None:
        return []
    n_components = min(n_topics, len(texts), tfidf.shape[1])
    model = NMF(n_components=n_components, random_state=42, max_iter=300)
    model.fit(tfidf)
    names = vectorizer.get_feature_names_out()
    return [
        " / ".join(names[i] for i in topic.argsort()[-3:][::-1])
        for topic in model.components_
    ]


def _topic_word_freq(texts: list[str], top_n: int = 30) -> dict[str, float]:
    """按全局 TF-IDF 权重取 top_n 词，供词云用。

    与 _nmf_topics 共用 _build_tfidf 预处理，但不做矩阵分解：词云要的是全局词重要度
    （矩阵列和），而非 NMF 的主题内载荷。返回 {词: 权重}，空词表返 {}。
    """
    if not texts:
        return {}

    import numpy as np

    vectorizer, tfidf = _build_tfidf(texts)
    if tfidf is None:
        return {}
    names = vectorizer.get_feature_names_out()
    weights = np.asarray(tfidf.sum(axis=0)).ravel()
    top = weights.argsort()[::-1][:top_n]
    return {names[i]: float(weights[i]) for i in top}


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
