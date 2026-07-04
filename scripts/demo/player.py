"""Demo replay player -- forces CCA_CACHE_MODE=replay, replaying the pre-recorded cache instantly.

Prerequisite: run runner.py --cache write once first to populate the cache.
This script never calls a real LLM, never writes cache, never goes online; every
node replays by deserializing messages from the SQLite cache.

Usage:
    $env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
    python scripts/demo/player.py [--target-product 飞书] [--user-query "..."] [--skip-report]
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
    p.add_argument("--skip-report", action="store_true", help="跳过 report 节点（demo 现场常用）")
    args = p.parse_args()

    # force replay; a cache miss raises immediately, prompting you to run the runner write-cache step first
    os.environ["CCA_CACHE_MODE"] = "replay"
    print("[player] CCA_CACHE_MODE=replay（未命中即抛错）", flush=True)

    graph = build_graph(include_report=not args.skip_report)
    state = empty_state(args.user_query, args.target_product)

    hr("PLAYER · cache replay 端到端")
    try:
        result = graph.invoke(state, config={"recursion_limit": 30})
    except RuntimeError as e:
        if "react_cache" in str(e):
            print(f"\n[player] cache miss: {e}", flush=True)
            print("提示：先用 runner.py --cache write 把缓存灌一次。", flush=True)
            sys.exit(2)
        raise

    if result.get("report_task"):
        dump_json("report_task（最终下发给 Reporter）", result["report_task"])
    show_decisions(result.get("decision_log") or [])
    summary(result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
