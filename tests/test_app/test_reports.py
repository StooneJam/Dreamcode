"""测试 /api/reports 列表与 /api/reports/{id} 回看的 owner 隔离（fixture 见 conftest）。"""
from __future__ import annotations


def test_reports_list_scoped_to_owner(env) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "md", "p")
    db.save_report("r2", "bob", "钉钉", "md", "p")
    resp = client.get("/api/reports", headers={"X-Owner": "alice"})
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()["reports"]] == ["r1"]   # 只看到自己的


def test_report_detail_includes_messages(env) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", "p")
    conv = db.get_or_create_conversation("r1", "alice")
    db.add_message(conv, "user", "Q")
    db.add_message(conv, "assistant", "A")

    resp = client.get("/api/reports/r1", headers={"X-Owner": "alice"})
    assert resp.status_code == 200
    assert resp.json()["report"]["report_md"] == "# 正文"
    assert [m["role"] for m in resp.json()["messages"]] == ["user", "assistant"]


def test_report_detail_isolated_returns_404(env) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", "p")
    resp = client.get("/api/reports/r1", headers={"X-Owner": "bob"})
    assert resp.status_code == 404                               # bob 看不到 alice 的报告
