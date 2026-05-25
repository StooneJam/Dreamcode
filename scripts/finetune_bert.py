"""BERT 领域微调脚本 —— 从 App Store 爬取评论后微调情感分类模型。

用法：
    python scripts/finetune_bert.py           # 使用缓存样本（若有）
    python scripts/finetune_bert.py --force   # 强制重新爬取
    python scripts/finetune_bert.py --dry-run # 仅爬取 + 统计，不训练
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cca.settings import load_config
from cca.skills.bert_finetune.collect import crawl_domain_samples, load_samples, save_samples
from cca.skills.bert_finetune.train import fine_tune

_SAMPLE_CACHE = Path("data/bert_finetune/samples.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="BERT 领域微调")
    parser.add_argument("--force", action="store_true", help="忽略样本缓存，重新爬取")
    parser.add_argument("--dry-run", action="store_true", help="仅爬取和统计，不执行训练")
    args = parser.parse_args()

    cfg = load_config()
    ft_cfg = cfg.get("nlp", {}).get("fine_tune", {})
    base_model: str = cfg["nlp"]["bert_model"]
    domain_apps: list[str] = ft_cfg.get("domain_apps", [])
    country: str = ft_cfg.get("country", "cn")
    min_samples: int = ft_cfg.get("min_samples", 200)
    epochs: int = ft_cfg.get("epochs", 3)
    output_dir: str = ft_cfg.get("model_output_dir", "data/models/bert_fine_tuned")

    if not domain_apps:
        print("错误：config.nlp.fine_tune.domain_apps 为空")
        sys.exit(1)

    # 样本阶段
    if not args.force and _SAMPLE_CACHE.exists():
        samples = load_samples(_SAMPLE_CACHE)
        print(f"从缓存加载 {len(samples)} 条样本：{_SAMPLE_CACHE}")
    else:
        print(f"爬取领域应用：{domain_apps}")
        samples = crawl_domain_samples(domain_apps, country=country)
        save_samples(samples, _SAMPLE_CACHE)
        print(f"爬取完成，共 {len(samples)} 条，已缓存至 {_SAMPLE_CACHE}")

    pos = sum(1 for s in samples if s.label == 2)
    neg = sum(1 for s in samples if s.label == 0)
    print(f"标签分布 — positive: {pos}，negative: {neg}")

    if len(samples) < min_samples:
        print(f"警告：样本数 {len(samples)} < min_samples {min_samples}，仍继续")

    if args.dry_run:
        print("--dry-run 模式，跳过训练")
        return

    # 训练阶段
    print(f"开始微调，base_model={base_model}，epochs={epochs}")
    saved_path = fine_tune(base_model, samples, output_dir, epochs=epochs)
    print(f"微调完成，模型已保存至：{saved_path}")
    print(f"将 config.yaml nlp.bert_model 设为该路径即可使用微调模型。")


if __name__ == "__main__":
    main()
