"""爬取领域 App Store 评论并自动按星级打标签，供 BERT 微调使用。

标签规则：4-5★ → positive(2)，1-2★ → negative(0)，3★ 跳过（噪音太多）。
"""
from __future__ import annotations

import json
from pathlib import Path

from cca.tools.appstore import _run_scraper


class LabeledSample:
    """单条带标签的文本样本。"""

    __slots__ = ("text", "label")

    def __init__(self, text: str, label: int) -> None:
        self.text = text
        self.label = label


def crawl_domain_samples(
    domain_apps: list[str],
    country: str = "cn",
    max_per_app: int = 100,
) -> list[LabeledSample]:
    """爬取若干领域 App 的评论，返回自动标注的样本列表。"""
    samples: list[LabeledSample] = []
    for app_name in domain_apps:
        data = _run_scraper(app_name, country, max_per_app)
        for review in data.get("reviews", []):
            text = f"{review.get('title', '')} {review.get('text', '')}".strip()
            rating = review.get("rating")
            if not text or rating is None:
                continue
            if rating >= 4:
                samples.append(LabeledSample(text, 2))  # positive
            elif rating <= 2:
                samples.append(LabeledSample(text, 0))  # negative
            # 3★ 跳过
    return samples


def save_samples(samples: list[LabeledSample], output_path: Path) -> None:
    """将样本写成 JSONL 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps({"text": s.text, "label": s.label}, ensure_ascii=False) + "\n")


def load_samples(path: Path) -> list[LabeledSample]:
    """从 JSONL 文件读回样本。"""
    samples = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            samples.append(LabeledSample(obj["text"], obj["label"]))
    return samples
