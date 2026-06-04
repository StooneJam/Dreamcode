"""scrape_local_life：Google Places Text Search + Top-N 加权平均（全程不触网）。"""
from __future__ import annotations

import json

import pytest

from cca.tools import places


def _fake_resp(body: dict):
    class R:
        def raise_for_status(self) -> None: ...
        def json(self) -> dict:
            return body
    return R()


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    """用内存 dict 替掉 sqlite 缓存，避免触碰 store.db。"""
    store: dict = {}

    def fake_get(node, key):
        return store.get(json.dumps(key, sort_keys=True))

    def fake_put(node, key, payload):
        store[json.dumps(key, sort_keys=True)] = payload

    monkeypatch.setattr(places.react_cache, "get", fake_get)
    monkeypatch.setattr(places.react_cache, "put", fake_put)


class TestAggregateRating:
    def test_weighted_average_by_review_count(self):
        results = [
            {"rating": 4.0, "user_ratings_total": 100},
            {"rating": 5.0, "user_ratings_total": 300},
        ]
        agg = places._aggregate_rating(results)
        assert agg["aggregate_rating"] == 4.75  # (4*100+5*300)/400
        assert agg["rating_review_count"] == 400
        assert agg["store_count"] == 2

    def test_skips_stores_without_rating_or_reviews(self):
        results = [
            {"rating": 4.5, "user_ratings_total": 10},
            {"rating": None, "user_ratings_total": 999},  # 无评分
            {"rating": 3.0, "user_ratings_total": 0},     # 无评论
            {"name": "缺字段"},
        ]
        agg = places._aggregate_rating(results)
        assert agg["aggregate_rating"] == 4.5
        assert agg["store_count"] == 1

    def test_top_n_caps_store_count(self):
        results = [{"rating": 5.0, "user_ratings_total": i + 1} for i in range(30)]
        assert places._aggregate_rating(results, top_n=20)["store_count"] == 20

    def test_no_usable_store_returns_none(self):
        assert places._aggregate_rating([]) is None
        assert places._aggregate_rating([{"rating": None, "user_ratings_total": 5}]) is None


class TestScrapeLocalLife:
    def test_missing_key_fails_soft(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
        out = json.loads(places.scrape_local_life.invoke({"brand": "蜜雪冰城"}))
        assert out["found"] is False
        assert "GOOGLE_MAPS_API_KEY" in out["note"]

    def test_success_returns_structured_rating(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
        body = {"status": "OK", "results": [
            {"rating": 4.0, "user_ratings_total": 100},
            {"rating": 4.5, "user_ratings_total": 100},
        ]}
        monkeypatch.setattr(places.httpx, "get", lambda *a, **k: _fake_resp(body))
        out = json.loads(places.scrape_local_life.invoke({"brand": "蜜雪冰城"}))
        assert out["found"] is True
        assert out["rating_source"] == "google_maps"
        assert out["aggregate_rating"] == 4.25
        assert out["rating_review_count"] == 200
        assert "google.com/maps/search/" in out["source_url"]

    def test_zero_results_found_false(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
        body = {"status": "ZERO_RESULTS", "results": []}
        monkeypatch.setattr(places.httpx, "get", lambda *a, **k: _fake_resp(body))
        out = json.loads(places.scrape_local_life.invoke({"brand": "纯大陆小品牌"}))
        assert out["found"] is False

    def test_api_error_found_false(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
        body = {"status": "REQUEST_DENIED", "error_message": "billing not enabled"}
        monkeypatch.setattr(places.httpx, "get", lambda *a, **k: _fake_resp(body))
        out = json.loads(places.scrape_local_life.invoke({"brand": "X"}))
        assert out["found"] is False
        assert "REQUEST_DENIED" in out["note"]

    def test_cache_hit_skips_second_http_call(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
        body = {"status": "OK", "results": [{"rating": 4.0, "user_ratings_total": 50}]}
        calls = {"n": 0}

        def counting_get(*a, **k):
            calls["n"] += 1
            return _fake_resp(body)

        monkeypatch.setattr(places.httpx, "get", counting_get)
        places.scrape_local_life.invoke({"brand": "蜜雪冰城"})
        places.scrape_local_life.invoke({"brand": "蜜雪冰城"})
        assert calls["n"] == 1
