"""App Store 工具测试 —— mock subprocess，不依赖 Node.js 或网络。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch



_FAKE_OUTPUT = {
    "product_name": "钉钉",
    "app_title": "钉钉",
    "app_id": 930368978,
    "country": "cn",
    "rating": 2.34,
    "review_count": 2800000,
    "reviews": [
        {"id": "1", "rating": 1, "title": "很卡", "text": "视频会议经常断线", "date": "2026-05-01"},
        {"id": "2", "rating": 5, "title": "好用", "text": "协同很方便消息通知及时", "date": "2026-05-02"},
        {"id": "3", "rating": 4, "title": "不错", "text": "免费版功能够用", "date": "2026-05-03"},
    ],
}


def _make_proc(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestRunScraper:
    def test_returns_parsed_dict(self):
        from cca.tools.appstore import _run_scraper

        with patch("subprocess.run", return_value=_make_proc(json.dumps(_FAKE_OUTPUT))):
            data = _run_scraper("钉钉", "cn", 50)

        assert data["rating"] == 2.34
        assert data["review_count"] == 2800000
        assert len(data["reviews"]) == 3

    def test_passes_args_to_node(self):
        from cca.tools.appstore import _run_scraper

        with patch("subprocess.run", return_value=_make_proc(json.dumps(_FAKE_OUTPUT))) as mock_run:
            _run_scraper("飞书", "us", 30)

        call_args = mock_run.call_args[0][0]
        assert "飞书" in call_args
        assert "us" in call_args
        assert "30" in call_args

    def test_returns_error_dict_on_empty_stdout_with_nonzero_exit(self):
        """子进程异常 → 返回 {'error': ...} 而非 raise（避免中断 ReAct）。"""
        from cca.tools.appstore import _run_scraper

        with patch("subprocess.run", return_value=_make_proc("", returncode=1, stderr="boom")):
            result = _run_scraper("不存在", "cn", 10)
        assert "error" in result
        assert "app-store-scraper" in result["error"]
        assert result["product_name"] == "不存在"

    def test_app_not_found_returns_error_field(self):
        from cca.tools.appstore import _run_scraper

        not_found = {"product_name": "X", "country": "cn", "rating": None,
                     "review_count": None, "reviews": [], "error": "app_not_found"}
        with patch("subprocess.run", return_value=_make_proc(json.dumps(not_found))):
            data = _run_scraper("X", "cn", 10)

        assert data["error"] == "app_not_found"
        assert data["rating"] is None


class TestScrapeAppStoreTool:
    def test_returns_json_string(self):
        from cca.tools.appstore import scrape_app_store

        with patch("subprocess.run", return_value=_make_proc(json.dumps(_FAKE_OUTPUT))):
            result = scrape_app_store.invoke({"product_name": "钉钉"})

        parsed = json.loads(result)
        assert parsed["rating"] == 2.34
        assert isinstance(parsed["reviews"], list)

    def test_max_reviews_capped_at_200(self):
        from cca.tools.appstore import scrape_app_store

        with patch("subprocess.run", return_value=_make_proc(json.dumps(_FAKE_OUTPUT))) as mock_run:
            scrape_app_store.invoke({"product_name": "钉钉", "max_reviews": 999})

        call_args = mock_run.call_args[0][0]
        assert "200" in call_args
