"""Dev / pre-recording demo runner -- runs the full pipeline for real (graph.invoke, straight through).

This script **always uses the real LLM**: running it is a real run. Mock/plumbing
smoke tests are scripts/demo/dry_run.py's job -- the two are kept separate.

Usage:
    $env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
    python scripts/demo/runner.py --cache write
    python scripts/demo/runner.py --cache auto --skip-report
    python scripts/demo/runner.py --seed-file docs/课题介绍.pdf --cache write
    python scripts/demo/runner.py --human-review
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from cca.demo._common import dump_json, hr, show_decisions, summary
from cca.graph import build_graph, empty_state
from cca.observability.logger import format_table, track_pipeline_tokens


def _prompt_human_review(payload: dict) -> dict:
    """When human_gate pauses via interrupt, show a summary in the CLI and collect one round of revision feedback."""
    hr("HUMAN REVIEW · 阶段 2.5 修订意见（仅一次）")
    print(f"  {payload.get('hint', '')}", flush=True)
    for row in payload.get("profiles", []):
        print(
            f"    - {row['product_name']}: {len(row['dimensions'])} 维度 {row['dimensions']}"
            f" | {row['review_count']} 评论 | 平台 {row['platforms']}",
            flush=True,
        )
    text = input("  修订意见（直接回车 = 无修订放行）: ").strip()
    return {"raw_feedback": text} if text else {"approved": True}


def _invoke_with_human_review(graph, state: Any, config: dict) -> dict:
    """Graph mode with human-in-the-loop: run until interrupt pauses -> CLI collects
    text -> Command(resume) continues, until there's no more interrupt."""
    from langgraph.types import Command
    result = graph.invoke(state, config=config)
    while "__interrupt__" in result:
        feedback = _prompt_human_review(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=feedback), config=config)
    return result


def _run_graph(args: argparse.Namespace) -> None:
    os.environ["CCA_CACHE_MODE"] = args.cache
    print(f"[runner] CCA_CACHE_MODE={args.cache}", flush=True)

    config: dict = {"recursion_limit": 30}
    if args.human_review:
        from langgraph.checkpoint.memory import MemorySaver
        os.environ["CCA_HUMAN_REVIEW"] = "1"
        graph = build_graph(include_report=not args.skip_report, checkpointer=MemorySaver())
        config["configurable"] = {"thread_id": "demo-human-review"}
        print("[runner] human-review 开启（interrupt/resume 闭环）", flush=True)
    else:
        graph = build_graph(include_report=not args.skip_report)
    state = empty_state(args.user_query, args.target_product, user_files=args.user_files)

    hr(f"RUNNER · graph mode (cache={args.cache})")
    with track_pipeline_tokens() as token_box:
        if args.human_review:
            result = _invoke_with_human_review(graph, state, config)
        else:
            result = graph.invoke(state, config=config)

    if result.get("domain_seed"):
        # only present when a user-uploaded doc was read and distilled -- its presence proves the PDF was ingested
        dump_json("domain_seed", result["domain_seed"])
    if result.get("exploration_result"):
        dump_json("exploration_result", result["exploration_result"])
    if result.get("task_plan"):
        dump_json("task_plan", result["task_plan"])
    if result.get("profiles"):
        # Collector writes dimensions/pricing/sources/website; Insight writes sentiment -- dump them together
        dump_json("profiles", result["profiles"])
    if result.get("report_task"):
        dump_json("report_task", result["report_task"])
    if result.get("audit_log"):
        # node-level event audit, for diagnosing intermediate steps like insight/finalize_sentiment
        dump_json("audit_log", result["audit_log"])
    show_decisions(result.get("decision_log") or [])
    summary(result)

    if token_box.get("usages"):
        hr("TOKEN 消耗 · 本次 pipeline 按模型")
        print(format_table(token_box["usages"]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-product", default="飞书")
    p.add_argument("--user-query", default="帮我分析飞书的主要竞品")
    p.add_argument("--cache", choices=["off", "write", "auto"], default="auto")
    p.add_argument("--skip-report", action="store_true")
    p.add_argument("--seed-file", type=str, default=None, help="用户上传文档路径")
    p.add_argument("--human-review", action="store_true",
                   help="开启阶段 2.5 人在环：interrupt 暂停收一次修订意见（需 checkpointer）")
    args = p.parse_args()
    args.user_files = [args.seed_file] if args.seed_file else None

    _run_graph(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
