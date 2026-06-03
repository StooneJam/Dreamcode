"""按 product_type 关键词映射评论抓取渠道。

对比对象一致性的核心：同一次竞品分析里 target + 全部竞品共享 task 级 product_type，
据此选定**唯一**渠道，避免「某产品恰好有 App 就去抓 App Store 评分、其余产品抓大众点评」
导致两边评价的根本不是同一个对象。无关键词命中时默认通用联网搜索——绝不默认 App Store。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Channel = Literal["app_store", "local_life", "ecommerce", "general"]


@dataclass
class ChannelRoute:
    """单个渠道的路由描述符，供 Insight 构造数据源指引。"""

    channel: Channel
    label: str            # 渠道中文名，写进 prompt
    platforms: list[str]  # 候选平台/搜索源，喂给 web_search
    use_app_store: bool   # 是否走 scrape_app_store


# 关键词 → 渠道，按特异性从高到低匹配：本地生活 / 电商 在前，App 在后。
# App 类关键词保持精确（软件/SaaS/客户端…），不收「平台」「应用」「工具」等泛词，避免误命中。
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
    """按 product_type 关键词选评论渠道；无命中默认通用搜索（不默认 App Store）。"""
    if not product_type:
        return _DEFAULT_ROUTE
    pt = product_type.lower()
    for keywords, route in _KEYWORD_ROUTES:
        if any(kw in pt for kw in keywords):
            return route
    return _DEFAULT_ROUTE
