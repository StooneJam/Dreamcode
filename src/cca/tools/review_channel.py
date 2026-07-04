"""Maps product_type keywords to a review-scraping channel.

The core of comparison-target consistency: within one competitive analysis run,
target + all competitors share a single task-level product_type, which picks a
**single** channel for all of them -- avoiding a situation where "this product
happens to have an app so we scrape App Store ratings, but the rest get scraped
from Dianping," which would compare fundamentally different things across products.
When no keyword matches, defaults to general web search -- never defaults to App Store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Channel = Literal["app_store", "local_life", "ecommerce", "general"]


@dataclass
class ChannelRoute:
    """A single channel's routing descriptor, used by Insight to build its data-source guidance."""

    channel: Channel
    label: str            # the channel's display name, written into the prompt
    platforms: list[str]  # candidate platforms/search sources, fed to web_search
    use_app_store: bool   # whether to go through scrape_app_store


# keyword -> channel, matched from most to least specific: local-life / e-commerce
# first, App last. App keywords are kept precise (software/SaaS/client...), excluding
# generic terms like "platform"/"application"/"tool" to avoid false matches.
_KEYWORD_ROUTES: list[tuple[tuple[str, ...], ChannelRoute]] = [
    (
        ("餐饮", "咖啡", "茶饮", "奶茶", "餐厅", "饭店", "到店", "门店", "连锁",
         "酒店", "民宿", "外卖", "烘焙", "火锅", "烧烤", "小吃", "线下"),
        ChannelRoute("local_life", "本地生活（大众点评/美团）",
                     ["大众点评", "美团", "小红书"], use_app_store=False),
    ),
    (
        ("美妆", "护肤", "化妆", "香水", "彩妆", "家电", "数码", "手机", "电脑",
         "服饰", "服装", "食品", "饮料", "零食", "快消", "母婴", "家居", "家具",
         "硬件", "实物", "商品", "电商"),
        ChannelRoute("ecommerce", "电商（天猫/京东/亚马逊）",
                     ["天猫", "京东", "亚马逊", "小红书"], use_app_store=False),
    ),
    (
        ("app", "软件", "saas", "小程序", "客户端", "移动应用", "手机应用",
         "应用程序", "ios", "android"),
        ChannelRoute("app_store", "App Store / 应用商店",
                     ["App Store", "知乎", "微博"], use_app_store=True),
    ),
]

_DEFAULT_ROUTE = ChannelRoute(
    "general", "通用联网搜索", [], use_app_store=False
)


def resolve_review_channel(product_type: str | None) -> ChannelRoute:
    """Pick a review channel from product_type keywords; defaults to general search on no match (never App Store)."""
    if not product_type:
        return _DEFAULT_ROUTE
    pt = product_type.lower()
    for keywords, route in _KEYWORD_ROUTES:
        if any(kw in pt for kw in keywords):
            return route
    return _DEFAULT_ROUTE
