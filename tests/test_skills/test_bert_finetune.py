"""BERT 微调 skill 测试 —— mock App Store 爬取，不依赖网络或 GPU。"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch


from cca.skills.bert_finetune.collect import LabeledSample, crawl_domain_samples, load_samples, save_samples


_FAKE_REVIEWS = {
    "reviews": [
        {"id": "1", "rating": 5, "title": "好用", "text": "协同效率高"},
        {"id": "2", "rating": 4, "title": "不错", "text": "消息通知及时"},
        {"id": "3", "rating": 1, "title": "差评", "text": "经常崩溃"},
        {"id": "4", "rating": 2, "title": "卡顿", "text": "视频会议卡"},
        {"id": "5", "rating": 3, "title": "一般", "text": "中规中矩"},  # 3★ 跳过
    ]
}


class TestLabeledSample:
    def test_slots(self):
        s = LabeledSample("test text", 2)
        assert s.text == "test text"
        assert s.label == 2


class TestCrawlDomainSamples:
    def test_labeling_rules(self):
        with patch("cca.skills.bert_finetune.collect._run_scraper", return_value=_FAKE_REVIEWS):
            samples = crawl_domain_samples(["钉钉"])

        labels = {s.text: s.label for s in samples}
        assert labels["好用 协同效率高"] == 2   # 5★ → positive
        assert labels["不错 消息通知及时"] == 2  # 4★ → positive
        assert labels["差评 经常崩溃"] == 0      # 1★ → negative
        assert labels["卡顿 视频会议卡"] == 0    # 2★ → negative
        # 3★ 跳过
        assert all("中规中矩" not in s.text for s in samples)

    def test_skips_reviews_with_no_text(self):
        reviews = {"reviews": [{"id": "1", "rating": 5, "title": "", "text": ""}]}
        with patch("cca.skills.bert_finetune.collect._run_scraper", return_value=reviews):
            samples = crawl_domain_samples(["X"])
        assert samples == []

    def test_multiple_apps_aggregated(self):
        with patch("cca.skills.bert_finetune.collect._run_scraper", return_value=_FAKE_REVIEWS):
            samples = crawl_domain_samples(["钉钉", "飞书"])
        # 每个 app 4 条（3★ 跳过），两个 app → 8 条
        assert len(samples) == 8


class TestSaveLoadSamples:
    def test_roundtrip(self):
        samples = [LabeledSample("好用协同", 2), LabeledSample("经常崩溃", 0)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "samples.jsonl"
            save_samples(samples, path)
            loaded = load_samples(path)

        assert len(loaded) == 2
        assert loaded[0].text == "好用协同"
        assert loaded[0].label == 2
        assert loaded[1].label == 0

    def test_save_creates_parent_dirs(self):
        samples = [LabeledSample("test", 2)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "samples.jsonl"
            save_samples(samples, path)
            assert path.exists()
