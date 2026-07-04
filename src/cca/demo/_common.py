"""Shared helper for the three demo scripts: printing, state persistence, CCAState summaries.

player.py / runner.py / dry_run.py each handle their own LLM patching; this file only holds pure I/O and display.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from cca.state import CCAState

_hr_start: float | None = None


def hr(title: str) -> None:
    """A section divider, auto-showing elapsed time since the first call."""
    global _hr_start
    if _hr_start is None:
        _hr_start = time.monotonic()
    secs = int(time.monotonic() - _hr_start)
    m, s = divmod(secs, 60)
    ts = f"+{m:02d}:{s:02d}"
    bar = "=" * 70
    print(f"\n{bar}\n  {title}  {ts}\n{bar}", flush=True)


def sub(title: str) -> None:
    print(f"\n  ── {title} ──", flush=True)


def dump_json(label: str, data: Any, indent: int = 4) -> None:
    """Print any JSON-serializable object."""
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    indented = "\n".join(" " * indent + line for line in text.splitlines())
    print(f"  {label}:\n{indented}", flush=True)


def show_decisions(log: list[dict]) -> None:
    if not log:
        return
    sub(f"DecisionRecord × {len(log)}")
    for d in log:
        print(f"    · [{d['phase']}/{d['decision_type']}] {d['rationale']}", flush=True)
        for alt in d.get("alternatives_considered") or []:
            print(f"        vs {alt['option']}: {alt['rejected_reason']}", flush=True)
        if d.get("inputs_used"):
            print(f"        inputs: {d['inputs_used']}", flush=True)


def _elapsed_str(start_ts: str | None, end_ts: str | None) -> str:
    """Convert two ISO 8601 UTC timestamps into a readable elapsed-time string."""
    if not start_ts:
        return "(未记录)"
    try:
        t0 = datetime.fromisoformat(start_ts)
        t1 = datetime.fromisoformat(end_ts) if end_ts else datetime.now(timezone.utc)
        secs = int((t1 - t0).total_seconds())
        m, s = divmod(secs, 60)
        return f"{m}分{s}秒" if m else f"{s}秒"
    except Exception:
        return "(计算失败)"


def summary(state: CCAState) -> None:
    """Final-state summary at END."""
    hr("END · 终态摘要")
    elapsed = _elapsed_str(state.get("analysis_start_ts"), state.get("analysis_end_ts"))
    print(f"  分析耗时: {elapsed}", flush=True)
    print(f"  decision_log: {len(state.get('decision_log') or [])} 条", flush=True)
    print(f"  debate_results: {len(state.get('debate_results') or [])} 条", flush=True)
    print(f"  audit_log: {len(state.get('audit_log') or [])} 条", flush=True)
    print(f"  profiles: {list((state.get('profiles') or {}).keys())}", flush=True)
    print(f"  report_status: {state.get('report_status')}", flush=True)
    print(f"  report_pdf: {state.get('report_pdf_path')}", flush=True)
    print(flush=True)
    print("  decision_log 摘要:", flush=True)
    for d in (state.get("decision_log") or []):
        did = d.get("decision_id", "?")
        print(f"    [{did}] {d['phase']}/{d['decision_type']} — {d['rationale'][:80]}", flush=True)
