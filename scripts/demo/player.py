"""答辩 demo 重放器 —— 强制 CCA_CACHE_MODE=replay，秒级重放预录缓存。

前置：先用 runner.py --cache write 跑过一次填缓存。
本脚本不调真 LLM、不写 cache、不联网；所有节点从 SQLite cache 反序列化 messages 重放。

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

    # 强制 replay；未命中节点直接抛错，提醒先 runner write cache
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
