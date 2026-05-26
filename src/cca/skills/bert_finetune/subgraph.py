"""BERT 微调编排入口 —— 爬取领域评论、打标签、训练并更新 config。

仅在首次或手动触发时执行，结果缓存到磁盘。
"""
from __future__ import annotations

from pathlib import Path

from cca.settings import PROJECT_ROOT, load_config
from cca.skills.bert_finetune.collect import crawl_domain_samples, load_samples, save_samples
from cca.skills.bert_finetune.train import fine_tune

_SAMPLE_CACHE = PROJECT_ROOT / "data" / "bert_finetune" / "samples.jsonl"


def run_finetune(force: bool = False) -> str:
    """运行完整微调流程，返回微调后模型路径。

    force=True 时忽略样本缓存，重新爬取。
    """
    cfg = load_config()
    ft_cfg = cfg.get("nlp", {}).get("fine_tune", {})

    base_model: str = cfg["nlp"]["bert_model"]
    domain_apps: list[str] = ft_cfg.get("domain_apps", [])
    country: str = ft_cfg.get("country", "cn")
    min_samples: int = ft_cfg.get("min_samples", 200)
    epochs: int = ft_cfg.get("epochs", 3)
    output_dir: str = ft_cfg.get("model_output_dir", "data/models/bert_fine_tuned")

    if not domain_apps:
        raise ValueError("config.nlp.fine_tune.domain_apps 为空，无法爬取领域数据")

    # 优先使用缓存样本
    if not force and _SAMPLE_CACHE.exists():
        samples = load_samples(_SAMPLE_CACHE)
    else:
        samples = crawl_domain_samples(domain_apps, country=country)
        save_samples(samples, _SAMPLE_CACHE)

    if len(samples) < min_samples:
        raise RuntimeError(
            f"样本数量不足：获得 {len(samples)} 条，要求 {min_samples} 条。"
            " 可增加 domain_apps 或降低 min_samples。"
        )

    return fine_tune(base_model, samples, output_dir, epochs=epochs)
