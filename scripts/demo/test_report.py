"""Quickly test Report Agent's output, skipping the upstream PM/Collector/Insight phases.

Usage:
    python scripts/demo/test_report.py
    python scripts/demo/test_report.py --target Feishu --competitors DingTalk WeCom
    python scripts/demo/test_report.py --reviewer          # enable Doubao final review
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cca.schema import (
    Dimension, Evidence, Fact, PricingInfo, PricingTier,
    ProductProfile, ReportTask, ReviewSample, ReviewUnit, UserSentiment,
)
from cca.graph import empty_state


def _ev(url: str, snippet: str) -> Evidence:
    return Evidence(source_url=url, snippet=snippet)


def _feishu() -> dict:
    return ProductProfile(
        product_name="飞书", company="字节跳动", website="https://www.feishu.cn",
        product_type="企业协作SaaS", target_users="中大型企业、互联网公司",
        dimensions=[
            Dimension(
                name="视频会议", category="功能",
                facts=[Fact(
                    statement="飞书视频会议企业版最大支持1000人，免费版不限时长",
                    evidence=[_ev("https://www.feishu.cn/product/meeting", "最大支持1000人，免费不限时")],
                )],
                cross_product_note="飞书免费版无时长限制，高于同类产品",
            ),
            Dimension(
                name="文档协作", category="功能",
                facts=[Fact(
                    statement="飞书文档支持多人实时协作，内置 AI 写作辅助与自动纪要",
                    evidence=[_ev("https://www.feishu.cn/product/docs", "飞书文档多人实时编辑")],
                )],
            ),
            Dimension(
                name="AI 能力", category="功能",
                facts=[Fact(
                    statement="飞书内置豆包 AI 助手，支持会议纪要自动生成、文档摘要、智能搜索",
                    evidence=[_ev("https://www.feishu.cn/product/ai", "飞书 AI 助手 powered by 豆包")],
                )],
            ),
            Dimension(
                name="平台支持", category="平台",
                facts=[Fact(
                    statement="飞书支持 Windows、macOS、iOS、Android，提供网页端，暂无 Linux 客户端",
                    evidence=[_ev("https://www.feishu.cn/download", "飞书全平台下载")],
                )],
            ),
            Dimension(
                name="交互设计", category="交互",
                facts=[Fact(
                    statement="飞书界面采用现代化设计语言，信息架构清晰，支持深色模式",
                    evidence=[_ev("https://www.feishu.cn", "飞书产品截图与设计规范")],
                )],
            ),
        ],
        pricing=PricingInfo(
            has_free_tier=True, pricing_model="per_user",
            tiers=[
                PricingTier(name="免费版", price_per_user_monthly=0, currency="CNY"),
                PricingTier(name="标准版", price_per_user_monthly=12, currency="CNY"),
                PricingTier(name="旗舰版", price_per_user_monthly=30, currency="CNY"),
            ],
        ),
        sentiment=UserSentiment(
            aggregate_rating=4.6, rating_review_count=85000,
            rating_source="appstore_cn",
            positive_themes=["界面设计现代", "文档协作流畅", "视频会议稳定", "AI 功能实用"],
            negative_themes=["功能复杂，上手成本高", "通知推送混乱", "与钉钉生态不兼容"],
            representative_reviews=[
                ReviewSample(text="文档协作是真的好用，多人编辑完全不卡。", rating=5, platform="appstore_cn"),
                ReviewSample(text="功能太多，新员工要适应一段时间。", rating=3, platform="appstore_cn"),
            ],
        ),
        sources=[_ev("https://www.feishu.cn", "飞书官网")],
    ).model_dump()


def _dingtalk() -> dict:
    return ProductProfile(
        product_name="钉钉", company="阿里巴巴", website="https://www.dingtalk.com",
        product_type="企业协作SaaS", target_users="中小企业、政府及教育机构",
        dimensions=[
            Dimension(
                name="视频会议", category="功能",
                facts=[Fact(
                    statement="钉钉免费版视频会议最多100人，限时30分钟；专业版解锁至300人无限时",
                    evidence=[_ev("https://www.dingtalk.com/pricing", "免费版100人限30分钟，专业版无限时")],
                )],
                cross_product_note="钉钉免费版视频有时长限制，需付费才能与飞书竞争",
            ),
            Dimension(
                name="AI 能力", category="功能",
                facts=[Fact(
                    statement="钉钉接入通义千问，提供 AI 助理、智能摘要、文档生成功能",
                    evidence=[_ev("https://www.dingtalk.com/ai", "钉钉 AI 助理 powered by 通义千问")],
                )],
            ),
            Dimension(
                name="平台支持", category="平台",
                facts=[Fact(
                    statement="钉钉支持 Windows、macOS、iOS、Android、网页端，另提供 Linux 版本",
                    evidence=[_ev("https://www.dingtalk.com/download", "钉钉全平台下载含 Linux")],
                )],
            ),
            Dimension(
                name="生态集成", category="生态",
                facts=[Fact(
                    statement="钉钉开放平台已接入超过2000款第三方应用，覆盖 OA、ERP、CRM 等",
                    evidence=[_ev("https://open.dingtalk.com", "钉钉开放平台：已上架 2000+ 应用")],
                )],
            ),
        ],
        pricing=PricingInfo(
            has_free_tier=True, pricing_model="per_user",
            tiers=[
                PricingTier(name="免费版", price_per_user_monthly=0, currency="CNY"),
                PricingTier(name="专业版", price_per_user_monthly=9, currency="CNY"),
                PricingTier(name="专属版", price_per_user_monthly=None, currency="CNY"),
            ],
        ),
        sentiment=UserSentiment(
            aggregate_rating=4.4, rating_review_count=210000,
            rating_source="appstore_cn",
            positive_themes=["使用普及广", "考勤打卡功能完善", "政企生态成熟"],
            negative_themes=["广告推广内容多", "界面相对老旧", "免费版限制明显"],
            representative_reviews=[
                ReviewSample(text="公司强制用，功能够用，广告有点烦。", rating=3, platform="appstore_cn"),
                ReviewSample(text="考勤和审批很完善，HR 用着很顺手。", rating=4, platform="appstore_cn"),
            ],
        ),
        sources=[_ev("https://www.dingtalk.com", "钉钉官网")],
    ).model_dump()


def _wecom() -> dict:
    return ProductProfile(
        product_name="企业微信", company="腾讯", website="https://work.weixin.qq.com",
        product_type="企业协作SaaS", target_users="需与微信生态打通的企业、零售及服务行业",
        dimensions=[
            Dimension(
                name="视频会议", category="功能",
                facts=[Fact(
                    statement="企业微信视频会议免费支持300人，无时长限制",
                    evidence=[_ev("https://work.weixin.qq.com", "企业微信会议300人免费无限时")],
                )],
            ),
            Dimension(
                name="微信生态联通", category="生态",
                facts=[Fact(
                    statement="企业微信客户联系可直接对接微信个人用户，支持朋友圈营销和客户群运营",
                    evidence=[_ev("https://work.weixin.qq.com/wework_admin/frame#customer", "客户联系功能直连微信")],
                )],
            ),
            Dimension(
                name="平台支持", category="平台",
                facts=[Fact(
                    statement="企业微信支持 iOS、Android、Windows、macOS 和网页端",
                    evidence=[_ev("https://work.weixin.qq.com/wework_admin/frame#index", "全平台客户端")],
                )],
            ),
        ],
        pricing=PricingInfo(
            has_free_tier=True, pricing_model="per_user",
            tiers=[
                PricingTier(name="免费版", price_per_user_monthly=0, currency="CNY", user_limit=200),
                PricingTier(name="服务商版", price_per_user_monthly=None, currency="CNY"),
            ],
        ),
        sentiment=UserSentiment(
            aggregate_rating=4.2, rating_review_count=95000,
            rating_source="appstore_cn",
            positive_themes=["与微信无缝衔接", "客户管理方便", "消息到达率高"],
            negative_themes=["内部协作功能偏弱", "文档能力较弱", "界面与微信重叠感强"],
            representative_reviews=[
                ReviewSample(text="做销售必用，客户管理比单用微信方便多了。", rating=5, platform="appstore_cn"),
                ReviewSample(text="内部协作不如飞书，主要靠它联系客户。", rating=3, platform="appstore_cn"),
            ],
        ),
        sources=[_ev("https://work.weixin.qq.com", "企业微信官网")],
    ).model_dump()


_PROFILES: dict[str, dict] = {
    "飞书": _feishu(),
    "钉钉": _dingtalk(),
    "企业微信": _wecom(),
}


def build_state(target: str, competitors: list[str], *, enable_reviewer: bool) -> dict:
    profiles = {name: _PROFILES[name] for name in [target] + competitors if name in _PROFILES}
    missing = [n for n in [target] + competitors if n not in _PROFILES]
    if missing:
        print(f"[warn] 以下产品无 mock 数据，已跳过：{missing}", flush=True)

    report_task = ReportTask(
        target_product=target,
        competitors=competitors,
        product_names=[target] + competitors,
        focus_dimensions=["视频会议", "AI 能力", "平台支持"],
        require_swot=True,
        cross_product_comparison_required=True,
        output_formats=["markdown", "pdf"],
        target_audience="产品负责人",
        sections=[],
        invoke_call_report_reviewer=enable_reviewer,
    ).model_dump()

    review_state = [
        ReviewUnit(agent="collector", product_name=name, status="passed", retry_count=0).model_dump()
        for name in profiles
    ]

    state = empty_state(
        user_query=f"分析{target}相对于{'、'.join(competitors)}的竞争优劣势",
        target_product=target,
    )
    state["profiles"] = profiles
    state["report_task"] = report_task
    state["review_state"] = review_state
    state["competitor_names"] = competitors
    return state


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default="飞书", help="目标分析产品（默认：飞书）")
    p.add_argument("--competitors", nargs="+", default=["钉钉", "企业微信"],
                   help="竞品列表（默认：钉钉 企业微信）")
    p.add_argument("--reviewer", action="store_true", help="启用豆包终审（需配置 DOUBAO_MODEL）")
    args = p.parse_args()

    state = build_state(args.target, args.competitors, enable_reviewer=args.reviewer)

    print(f"[test_report] target={args.target}  competitors={args.competitors}", flush=True)
    print(f"[test_report] profiles={list(state['profiles'].keys())}", flush=True)
    print("[test_report] calling report_node ...\n", flush=True)

    from cca.agents.qa_report import report_node
    result = report_node(state)

    print(f"\n{'='*60}")
    print(f"status : {result.get('report_status')}")
    print(f"pdf    : {result.get('report_pdf_path')}")
    if result.get("report_md"):
        md_path = Path(f"output/report_{args.target}.md")
        md_path.parent.mkdir(exist_ok=True)
        md_path.write_text(result["report_md"], encoding="utf-8")
        print(f"md     : {md_path}")
        print(f"\n--- MD 预览（前600字）---")
        print(result["report_md"][:600])
        print("...")


if __name__ == "__main__":
    main()
