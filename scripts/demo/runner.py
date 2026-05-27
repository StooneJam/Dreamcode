"""开发 / 预录用 demo runner —— 真 LLM 跑全流程，可选写 cache 供 player.py replay。

Usage:
    $env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
    python scripts/demo/runner.py --cache write          # 一次性预跑填 cache
    python scripts/demo/runner.py --cache auto           # 开发期，命中即重放、miss 真跑+写
    python scripts/demo/runner.py --cache off            # 纯真跑，不读不写
    python scripts/demo/runner.py --skip-report          # 跳过 Reporter 省 token
"""
from __future__ import annotations

import argparse
import os
import sys

from cca.graph import build_graph, empty_state

from cca.demo._common import dump_json, hr, show_decisions, summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-product", default="飞书")
    p.add_argument("--user-query", default="帮我分析飞书的主要竞品")
    p.add_argument("--cache", choices=["off", "write", "auto"], default="auto")
    p.add_argument("--skip-report", action="store_true")
    args = p.parse_args()

    os.environ["CCA_CACHE_MODE"] = args.cache
    print(f"[runner] CCA_CACHE_MODE={args.cache}", flush=True)

    graph = build_graph(include_report=not args.skip_report)
    state = empty_state(args.user_query, args.target_product)

    hr(f"RUNNER · live LLM (cache={args.cache})")
    result = graph.invoke(state, config={"recursion_limit": 30})

    if result.get("report_task"):
        dump_json("report_task", result["report_task"])
    show_decisions(result.get("decision_log") or [])
    summary(result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
