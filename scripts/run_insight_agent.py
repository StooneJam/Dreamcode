"""Insight Agent 测试脚本 —— 逐步执行完整分析管道并打印每步结果。

模式：
    python scripts/run_insight_agent.py              # 真实模式：联网 + 真实 LLM + 真实 NLP
    python scripts/run_insight_agent.py --mock       # 离线模式：全程假数据，不消耗 API

真实模式执行顺序（每个产品独立跑）：
    Step 1  scrape_app_store         → Node.js 爬取 App Store 评分与评论
    Step 2  get_or_create_questionnaire → LLM 设计问卷（或从 SQLite 缓存读取）
    Step 3  collect_responses        → LLM 模拟 5 个用户画像填写问卷
    Step 4  anonymize_responses      → PII 脱敏
    Step 5  web_search               → Tavily 搜索真实用户评论（知乎 / 微博）
    Step 6  analyze_sentiment_bert   → BERT 三分类情感标注
    Step 7  extract_topics (×2)      → NMF 分别提取正面 / 负面主题
    Step 8  UserSentiment            → 整合输出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root / "tests"))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
os.chdir(_root)


# ---------------------------------------------------------------------------
# 输入配置（可在此直接改产品和维度）
# ---------------------------------------------------------------------------

PRODUCTS = [
    {
        "name": "钉钉",
        "competitors": ["企业微信", "飞书"],
        "dimensions": ["协同效率", "视频会议", "定价"],
        "platforms": ["appstore_cn", "zhihu"],
    },
    {
        "name": "企业微信",
        "competitors": ["钉钉", "飞书"],
        "dimensions": ["企业集成", "稳定性", "移动端体验"],
        "platforms": ["appstore_cn", "weibo"],
    },
]


# ---------------------------------------------------------------------------
# 打印工具
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def _step(n: int, title: str) -> None:
    print(f"\n  [Step {n}] {title}")
    print(f"  {'-' * 44}")


# ---------------------------------------------------------------------------
# 真实管道（逐步执行，每步打印结果）
# ---------------------------------------------------------------------------

def run_real_pipeline() -> None:
    from cca.settings import load_config
    from cca.skills.questionnaire.collect import collect_responses, get_or_create_questionnaire
    from cca.skills.questionnaire.anonymize import anonymize_responses
    from cca.tools.appstore import _run_scraper
    from cca.tools.search import web_search
    from cca.tools.nlp_utils import _nmf_topics, _bert_sentiment
    from cca.schema import Evidence, ReviewSample, UserSentiment

    cfg = load_config()
    nlp_cfg = cfg.get("nlp", {})
    sentiment_model = nlp_cfg.get("sentiment_model", "llm")
    bert_model = nlp_cfg.get(
        "bert_model",
        "lxyuan/distilbert-base-multilingual-cased-sentiments-student",
    )
    fill_mode = cfg.get("questionnaire", {}).get("fill_mode", "llm")
    n_responses = cfg.get("questionnaire", {}).get("n_llm_responses", 5)

    print(f"\n配置：fill_mode={fill_mode}  sentiment_model={sentiment_model}  n_responses={n_responses}")

    all_results: dict[str, dict] = {}

    for prod in PRODUCTS:
        name = prod["name"]
        _section(f"产品：{name}")

        # ------------------------------------------------------------------
        # Step 1：App Store 爬取
        # ------------------------------------------------------------------
        _step(1, "App Store 爬取（Node.js app-store-scraper）")
        appstore_rating: float | None = None
        appstore_review_count: int | None = None
        appstore_texts: list[str] = []
        appstore_reviews_raw: list[dict] = []
        try:
            appstore_data = _run_scraper(name, "cn", 50)
            if appstore_data.get("error"):
                print(f"  未找到 App（{appstore_data['error']}），跳过评分")
            else:
                appstore_rating = appstore_data.get("rating")
                appstore_review_count = appstore_data.get("review_count")
                appstore_reviews_raw = appstore_data.get("reviews", [])
                appstore_texts = [
                    f"{r.get('title', '')} {r.get('text', '')}".strip()
                    for r in appstore_reviews_raw
                    if r.get("text")
                ]
                print(f"  App：{appstore_data.get('app_title')}  评分：{appstore_rating}  总评论数：{appstore_review_count}")
                print(f"  爬取评论：{len(appstore_texts)} 条")
                for r in appstore_reviews_raw[:2]:
                    print(f"    [{r.get('rating')}★] {r.get('text', '')[:60]}")
        except Exception as e:
            print(f"  App Store 爬取失败：{e}（继续后续步骤）")

        # ------------------------------------------------------------------
        # Step 2：问卷设计（缓存 or LLM）
        # ------------------------------------------------------------------
        _step(2, "问卷设计（SQLite 缓存 / LLM 生成）")
        questionnaire = get_or_create_questionnaire(
            product_name=name,
            competitor_names=prod["competitors"],
            dimensions=prod["dimensions"],
        )
        print(f"  题目数量：{len(questionnaire.questions)}")
        for q in questionnaire.questions:
            opts = f"  选项：{q.options}" if q.options else ""
            print(f"    [{q.id}] {q.q_type:16s} {q.text}{opts}")

        # ------------------------------------------------------------------
        # Step 3：问卷填写（LLM 模拟用户）
        # ------------------------------------------------------------------
        _step(3, f"问卷填写（fill_mode={fill_mode}，n={n_responses}）")
        raw_responses = collect_responses(questionnaire, n=n_responses, fill_mode=fill_mode)
        if not raw_responses:
            print("  real 模式：问卷已格式化供真实用户填写，跳过 LLM 填写")
        else:
            print(f"  收到 {len(raw_responses)} 份回答，示例（第 1 份）：")
            for ans in raw_responses[0].answers[:3]:
                print(f"    [{ans.question_id}] {ans.answer[:60]}")

        # ------------------------------------------------------------------
        # Step 4：PII 脱敏
        # ------------------------------------------------------------------
        _step(4, "PII 脱敏（手机号 / 邮箱 / 身份证）")
        clean_responses = anonymize_responses(raw_responses) if raw_responses else []
        if clean_responses:
            print(f"  脱敏后 respondent_id 样本：{clean_responses[0].respondent_id}")
        else:
            print("  无回答需脱敏")

        survey_texts: list[str] = [
            ans.answer
            for resp in clean_responses
            for ans in resp.answers
            if ans.answer.strip()
        ]

        # ------------------------------------------------------------------
        # Step 5：联网搜索真实评论
        # ------------------------------------------------------------------
        _step(5, "联网搜索用户评论（Tavily）")
        search_results: list[dict] = []
        queries = [
            f"{name} 用户评价 体验 知乎",
        ]
        for query in queries:
            print(f"  搜索：{query}")
            hits = web_search.invoke({"query": query, "max_results": 5})
            search_results.extend(hits)
            for h in hits[:2]:
                snippet = (h.get("content") or "")[:80].replace("\n", " ")
                print(f"    [{h.get('url', '')[:40]}]  {snippet}")

        web_texts: list[str] = [
            (h.get("content") or "")[:200]
            for h in search_results
            if h.get("content")
        ]
        all_texts = appstore_texts + survey_texts + web_texts
        print(f"  合计文本：{len(all_texts)}（AppStore {len(appstore_texts)} + 问卷 {len(survey_texts)} + 网络 {len(web_texts)}）")

        # ------------------------------------------------------------------
        # Step 6：BERT 情感分类
        # ------------------------------------------------------------------
        positive_themes: list[str] = []
        negative_themes: list[str] = []

        if sentiment_model == "bert" and all_texts:
            _step(6, f"BERT 情感分类（{bert_model}）")
            print("  首次运行会下载模型约 250 MB，请等待...")
            try:
                groups = _bert_sentiment(all_texts, bert_model)
                pos_count = len(groups["positive"])
                neg_count = len(groups["negative"])
                neu_count = len(groups["neutral"])
                print(f"  positive：{pos_count} 条  negative：{neg_count} 条  neutral：{neu_count} 条")

                # ----------------------------------------------------------
                # Step 7：NMF 主题提取（分正负两组）
                # ----------------------------------------------------------
                _step(7, "NMF 主题提取（分正面 / 负面组）")
                positive_themes = _nmf_topics(groups["positive"], n_topics=3)
                negative_themes = _nmf_topics(groups["negative"], n_topics=3)
                print(f"  正面主题：{positive_themes}")
                print(f"  负面主题：{negative_themes}")
            except Exception as e:
                print(f"  BERT 未能运行（{e}），回退到全量 NMF 拆分")
                topics = _nmf_topics(all_texts, n_topics=6)
                mid = len(topics) // 2
                positive_themes = topics[:mid] or topics
                negative_themes = topics[mid:] or topics
        else:
            _step(6, "LLM 情感判断（跳过 BERT）")
            topics = _nmf_topics(all_texts, n_topics=6) if all_texts else []
            mid = len(topics) // 2
            positive_themes = topics[:mid] or topics[:2]
            negative_themes = topics[mid:] or topics[-2:]
            print(f"  正面主题（NMF 前半段）：{positive_themes}")
            print(f"  负面主题（NMF 后半段）：{negative_themes}")
            _step(7, "NMF 主题提取（已在 Step 6 完成）")
            print("  跳过（BERT 未启用）")

        # ------------------------------------------------------------------
        # Step 8：整合 UserSentiment
        # ------------------------------------------------------------------
        _step(8, "整合 UserSentiment")
        sources = [
            Evidence(
                source_url=h.get("url", ""),
                snippet=(h.get("content") or "")[:120],
                fetched_at="2026-05-25T00:00:00Z",
            )
            for h in search_results[:3]
            if h.get("url")
        ]
        rep_reviews = [
            ReviewSample(
                text=(r.get("text") or "")[:100],
                platform="appstore_cn",
                source=Evidence(
                    source_url=f"https://apps.apple.com/cn/app/id{r.get('id', '')}",
                    snippet=(r.get("text") or "")[:80],
                    fetched_at="2026-05-25T00:00:00Z",
                ),
            )
            for r in appstore_reviews_raw[:3]
            if r.get("text")
        ]

        sentiment = UserSentiment(
            appstore_cn_rating=appstore_rating,
            appstore_cn_review_count=appstore_review_count,
            appstore_region="cn",
            positive_themes=positive_themes,
            negative_themes=negative_themes,
            representative_reviews=rep_reviews,
            sources=sources,
        )
        print(f"  AppStore 评分：{sentiment.appstore_cn_rating}（{sentiment.appstore_cn_review_count} 条评论）")
        print(f"  positive_themes：{sentiment.positive_themes}")
        print(f"  negative_themes：{sentiment.negative_themes}")
        print(f"  代表性评论数：{len(sentiment.representative_reviews)}")
        all_results[name] = sentiment.model_dump()

    # 最终汇总
    _section("全部产品 UserSentiment 汇总")
    for name, s in all_results.items():
        print(f"\n  {name}")
        print(f"    AppStore：{s.get('appstore_cn_rating')}  评论数：{s.get('appstore_cn_review_count')}")
        print(f"    正面：{s.get('positive_themes')}")
        print(f"    负面：{s.get('negative_themes')}")


# ---------------------------------------------------------------------------
# Mock 管道（全程假数据，不调任何外部服务）
# ---------------------------------------------------------------------------

def run_mock_pipeline() -> None:
    from cca.schema import Evidence, ReviewSample, UserSentiment
    from cca.tools.nlp_utils import _nmf_topics

    FAKE_TEXTS = {
        "钉钉": [
            "协同效率很高 消息通知及时 审批流程方便",
            "视频会议偶尔卡顿 画面不够清晰",
            "免费版功能足够用 性价比高",
            "移动端体验好 随时处理工作",
            "客服响应慢 问题处理不及时",
        ],
        "企业微信": [
            "和微信生态打通 联系客户很方便",
            "企业管理功能强大 权限设置灵活",
            "偶有消息延迟 影响沟通效率",
            "界面比较朴素 操作学习成本低",
            "直播功能稳定 适合大型会议",
        ],
    }

    for prod in PRODUCTS:
        name = prod["name"]
        _section(f"产品：{name}  [MOCK]")

        _step(1, "App Store 爬取（mock）")
        print(f"  mock 评分：{4.2 if name == '钉钉' else 4.0}  mock 评论数：10000")

        _step(2, "问卷设计（mock）")
        print("  mock 问卷：3 题（rating_5 / multiple_choice / open_text）")

        _step(3, "问卷填写（mock）")
        print(f"  mock 回答：{len(FAKE_TEXTS[name])} 条")

        _step(4, "PII 脱敏（mock）")
        print("  respondent_id → anon_user001")

        _step(5, "联网搜索（mock，跳过 Tavily）")
        print("  返回 0 条假搜索结果")

        texts = FAKE_TEXTS[name]
        pos = texts[:3]
        neg = texts[3:]

        _step(6, "BERT 情感分类（mock 分组）")
        print(f"  mock: positive {len(pos)} 条  negative {len(neg)} 条")

        _step(7, "NMF 主题提取（真实 sklearn）")
        positive_themes = _nmf_topics(pos, n_topics=2)
        negative_themes = _nmf_topics(neg, n_topics=2)
        print(f"  正面主题：{positive_themes}")
        print(f"  负面主题：{negative_themes}")

        _step(8, "整合 UserSentiment（mock）")
        s = UserSentiment(
            appstore_cn_rating=4.2 if name == "钉钉" else 4.0,
            appstore_cn_review_count=10000,
            appstore_region="cn",
            positive_themes=positive_themes,
            negative_themes=negative_themes,
            representative_reviews=[
                ReviewSample(text=texts[0][:60], platform="appstore_cn")
            ],
        )
        print(f"  positive_themes：{s.positive_themes}")
        print(f"  negative_themes：{s.negative_themes}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Insight Agent 分步测试")
    parser.add_argument(
        "--mock", action="store_true",
        help="离线模式：NMF 用真实 sklearn，其余全部 mock，不消耗 API",
    )
    args = parser.parse_args()

    if args.mock:
        print("离线 mock 模式（NMF 真实运行，其余跳过外部调用）")
        run_mock_pipeline()
    else:
        print("真实模式（App Store 爬取 + LLM 问卷 + Tavily 联网 + BERT + NMF）")
        print("首次运行 BERT 会下载模型约 250 MB，请确保网络通畅")
        print("确保已在 scripts/node/ 执行过 npm install")
        run_real_pipeline()


if __name__ == "__main__":
    main()
