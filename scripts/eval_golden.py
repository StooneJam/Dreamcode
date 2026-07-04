"""离线回归评估：跑 tests/golden 里的 case，检查 Collector/Insight 产出的结构完整性。

用法：
    python scripts/eval_golden.py

只跑到 human_gate（不生成报告，不建 checkpointer，直接放行），聚焦 Collector 联网
采集 + Insight 情感分析这两段最容易被 prompt/模型改动影响的产出。

PM 的 initial_brief / task_plan 不走 react_cache（见 cca/agents/pm.py），每次都是真实
LLM 调用，因此本脚本每次运行都会产生少量真实 API 开销（2 次 gpt-5 短调用）；下游
Collector 的 ReAct 调用走 CCA_CACHE_MODE=auto——命中则免费重放，未命中则真跑并写入
缓存供下次复用。想强制全部重放（不允许任何真实调用），改成 CCA_CACHE_MODE=replay，
未命中会直接报错提示你先用 --cache write 跑一次。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_GOLDEN_DIR = _PROJECT_ROOT / "tests" / "golden" / "cases"


def _load_cases() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_GOLDEN_DIR.glob("*.json"))]


def _evaluate(case: dict, result: dict) -> list[str]:
    """结构完整性检查，复用 call_report_reviewer 的溯源思路：数据必须可回查来源。"""
    failed: list[str] = []
    profiles = result.get("profiles") or {}
    target = case["target_product"]

    if target not in profiles:
        failed.append(f"目标产品 {target!r} 未出现在 profiles 中")
    if len(profiles) < case.get("min_competitors", 1):
        failed.append(f"竞品数量 {len(profiles)} 少于要求的 {case['min_competitors']}")

    for name, profile in profiles.items():
        if not profile.get("dimensions"):
            failed.append(f"[{name}] dimensions 为空")
        if not profile.get("sources"):
            failed.append(f"[{name}] sources 为空——数据无法溯源")
        if profile.get("sentiment") is None:
            failed.append(f"[{name}] sentiment 未填写，Insight 可能未完整跑完")

    return failed


def _run_case(case: dict) -> dict:
    from cca.graph import build_graph, empty_state

    state = empty_state(case["user_query"], case["target_product"])
    graph = build_graph(include_report=False)  # 无 checkpointer：human_gate 自动放行
    return graph.invoke(state, config={"recursion_limit": 40})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", choices=["auto", "replay"], default="auto")
    args = p.parse_args()

    os.environ["CCA_CACHE_MODE"] = args.cache  # 必须在 import cca.* 之前设置
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

    cases = _load_cases()
    if not cases:
        print(f"未找到 golden case（{_GOLDEN_DIR}）")
        sys.exit(1)

    any_failed = False
    for case in cases:
        try:
            result = _run_case(case)
            failed = _evaluate(case, result)
        except Exception as exc:
            failed = [f"运行异常：{exc}"]

        any_failed = any_failed or bool(failed)
        print(f"[{'FAIL' if failed else 'PASS'}] {case['id']}")
        for f in failed:
            print(f"    - {f}")

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
