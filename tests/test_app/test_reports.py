"""测试 /api/reports 列表与 /api/reports/{id} 回看的 owner 隔离（fixture 见 conftest）。"""
from __future__ import annotations


def test_reports_list_scoped_to_owner(env, auth) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "md", "p")
    db.save_report("r2", "bob", "钉钉", "md", "p")
    resp = client.get("/api/reports", headers=auth("alice"))
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()["reports"]] == ["r1"]   # 只看到自己的


def test_report_detail_includes_messages(env, auth) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", "p")
    conv = db.get_or_create_conversation("r1", "alice")
    db.add_message(conv, "user", "Q")
    db.add_message(conv, "assistant", "A")

    resp = client.get("/api/reports/r1", headers=auth("alice"))
    assert resp.status_code == 200
    assert resp.json()["report"]["report_md"] == "# 正文"
    assert [m["role"] for m in resp.json()["messages"]] == ["user", "assistant"]


def test_report_detail_isolated_returns_404(env, auth) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", "p")
    resp = client.get("/api/reports/r1", headers=auth("bob"))
    assert resp.status_code == 404                               # bob 看不到 alice 的报告


def test_run_trace_returns_events_for_owner(env, auth) -> None:
    client, db = env
    db.save_run_trace("r1", "alice", None, '[{"type":"log","agent":"PM Agent","text":"start"}]')
    resp = client.get("/api/reports/r1/trace", headers=auth("alice"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == [{"type": "log", "agent": "PM Agent", "text": "start"}]
    assert body["trace_url"] is None                             # 测试环境未开 LANGSMITH_TRACING


def test_run_trace_isolated_returns_404(env, auth) -> None:
    client, db = env
    db.save_run_trace("r1", "alice", None, "[]")
    assert client.get("/api/reports/r1/trace", headers=auth("bob")).status_code == 404
    assert client.get("/api/reports/nope/trace", headers=auth("alice")).status_code == 404
