"""demo 三脚本共享 helper：打印、state 落盘、CCAState 摘要。

player.py / runner.py / dry_run.py 各自负责自己的 LLM patching，本文件只放纯 I/O 与展示。
"""
from __future__ import annotations

import json
from typing import Any

from cca.state import CCAState


def hr(title: str) -> None:
    """段块分隔线。"""
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}", flush=True)


def sub(title: str) -> None:
    print(f"\n  ── {title} ──", flush=True)


def dump_json(label: str, data: Any, indent: int = 4) -> None:
    """打印任意 JSON 可序列化对象。"""
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


def summary(state: CCAState) -> None:
    """END 终态摘要。"""
    hr("END · 终态摘要")
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
