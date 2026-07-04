"""resolve_review_channel: maps product_type -> a review-scraping channel."""
from __future__ import annotations

from cca.tools.review_channel import resolve_review_channel


class TestLocalLife:
    def test_coffee_routes_to_local_life(self):
        assert resolve_review_channel("连锁咖啡").channel == "local_life"

    def test_local_life_does_not_use_app_store(self):
        assert resolve_review_channel("连锁咖啡").use_app_store is False

    def test_restaurant_routes_to_local_life(self):
        assert resolve_review_channel("餐饮连锁品牌").channel == "local_life"

    def test_local_life_wins_over_app_when_both_present(self):
        # the "Lucky Coffee" scenario: a brand has its own app, but the comparison
        # object is coffee -> must go through local-life, not scrape App Store
        assert resolve_review_channel("连锁咖啡App").channel == "local_life"


class TestEcommerce:
    def test_cosmetics_routes_to_ecommerce(self):
        assert resolve_review_channel("美妆护肤").channel == "ecommerce"

    def test_perfume_routes_to_ecommerce(self):
        assert resolve_review_channel("香水").channel == "ecommerce"

    def test_appliance_routes_to_ecommerce(self):
        assert resolve_review_channel("小家电").channel == "ecommerce"

    def test_ecommerce_does_not_use_app_store(self):
        assert resolve_review_channel("美妆护肤").use_app_store is False


class TestAppStore:
    def test_software_routes_to_app_store(self):
        assert resolve_review_channel("协同办公软件").channel == "app_store"

    def test_saas_routes_to_app_store(self):
        assert resolve_review_channel("SaaS 协作工具").channel == "app_store"

    def test_app_store_uses_app_store(self):
        assert resolve_review_channel("移动应用").use_app_store is True


class TestGeneralFallback:
    def test_none_routes_to_general(self):
        assert resolve_review_channel(None).channel == "general"

    def test_empty_routes_to_general(self):
        assert resolve_review_channel("").channel == "general"

    def test_unknown_routes_to_general(self):
        assert resolve_review_channel("区块链浏览器").channel == "general"

    def test_general_never_defaults_to_app_store(self):
        # core regression guard: an unknown category must never default to App Store
        assert resolve_review_channel("某种全新形态产品").use_app_store is False
