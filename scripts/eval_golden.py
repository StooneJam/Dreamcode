"""Offline regression eval: runs the cases in tests/golden and checks the structural
completeness of Collector/Insight output.

Usage:
    python scripts/eval_golden.py

Only runs up to human_gate (no report generation, no checkpointer, passes straight
through), focusing on Collector's web collection + Insight's sentiment analysis --
the two stages most sensitive to prompt/model changes.

PM's initial_brief / task_plan don't go through react_cache (see cca/agents/pm.py),
so every run makes real LLM calls (2 short gpt-5 calls); this script always incurs a
small real API cost. Downstream, Collector's ReAct calls use
CCA_CACHE_MODE=auto -- a hit replays for free, a miss runs for real and writes to
cache for next time. To force full replay (no real calls allowed), switch to
CCA_CACHE_MODE=replay; a miss will error out and tell you to run with --cache write first.
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
    """Structural completeness check, reusing call_report_reviewer's traceability idea: data must be traceable to a source."""
    failed: list[str] = []
    profiles = result.get("profiles") or {}
    target = case["target_product"]

    if target not in profiles:
        failed.append(f"target product {target!r} not found in profiles")
    if len(profiles) < case.get("min_competitors", 1):
        failed.append(f"competitor count {len(profiles)} is below the required {case['min_competitors']}")

    for name, profile in profiles.items():
        if not profile.get("dimensions"):
            failed.append(f"[{name}] dimensions is empty")
        if not profile.get("sources"):
            failed.append(f"[{name}] sources is empty -- data isn't traceable")
        if profile.get("sentiment") is None:
            failed.append(f"[{name}] sentiment isn't filled in, Insight may not have finished")

    return failed


def _run_case(case: dict) -> dict:
    from cca.graph import build_graph, empty_state

    state = empty_state(case["user_query"], case["target_product"])
    graph = build_graph(include_report=False)  # no checkpointer: human_gate passes straight through
    return graph.invoke(state, config={"recursion_limit": 40})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", choices=["auto", "replay"], default="auto")
    args = p.parse_args()

    os.environ["CCA_CACHE_MODE"] = args.cache  # must be set before importing cca.*
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

    cases = _load_cases()
    if not cases:
        print(f"no golden cases found ({_GOLDEN_DIR})")
        sys.exit(1)

    any_failed = False
    for case in cases:
        try:
            result = _run_case(case)
            failed = _evaluate(case, result)
        except Exception as exc:
            failed = [f"run failed: {exc}"]

        any_failed = any_failed or bool(failed)
        print(f"[{'FAIL' if failed else 'PASS'}] {case['id']}")
        for f in failed:
            print(f"    - {f}")

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
