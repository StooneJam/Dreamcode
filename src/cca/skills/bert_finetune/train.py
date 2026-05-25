"""BERT 微调 —— 使用 HuggingFace Trainer 在领域样本上继续训练情感分类模型。

label 映射：0 → negative，1 → neutral（未使用，仅占位），2 → positive。
微调后模型保存到 config 指定路径，下次启动自动使用微调版。
"""
from __future__ import annotations

from pathlib import Path

from cca.skills.bert_finetune.collect import LabeledSample


def _build_dataset(samples: list[LabeledSample], tokenizer):
    """构建 HuggingFace Dataset，做 tokenize。"""
    from datasets import Dataset  # type: ignore[import]

    data = {"text": [s.text for s in samples], "labels": [s.label for s in samples]}
    ds = Dataset.from_dict(data)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=256, padding="max_length")

    return ds.map(tokenize, batched=True, remove_columns=["text"])


def fine_tune(
    base_model: str,
    samples: list[LabeledSample],
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 16,
) -> str:
    """微调 BERT 模型并保存，返回 output_dir 路径字符串。

    需要 transformers、datasets、torch 已安装。
    """
    from transformers import (  # type: ignore[import]
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=3)

    ds = _build_dataset(samples, tokenizer)
    split = ds.train_test_split(test_size=0.1, seed=42)

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        logging_steps=50,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
    )
    trainer.train()

    out = Path(output_dir)
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    return str(out)
