"""测试 /api/jobs/{id}/question 的 DB 持久化 + owner 隔离（fixture 见 conftest）。"""
from __future__ import annotations


def test_question_persists_history_and_grounds(env) -> None:
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 飞书报告正文", "p.pdf")

    r1 = client.post("/api/jobs/job1/question",
                     json={"question": "定价多少?"}, headers={"X-Owner": "alice"})
    assert r1.status_code == 200
    assert "定价多少?" in r1.json()["answer"]          # 本轮问题进了上下文

    client.post("/api/jobs/job1/question",
                json={"question": "那钉钉?"}, headers={"X-Owner": "alice"})
    conv = db.get_or_create_conversation("job1", "alice")
    msgs = db.get_messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "定价多少?"            # 两轮都落库


def test_question_owner_isolation(env) -> None:
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 正文", "p")
    r = client.post("/api/jobs/job1/question",
                    json={"question": "x"}, headers={"X-Owner": "bob"})
    assert "无权访问" in r.json()["answer"]            # bob 访问不到 alice 的报告


def test_question_empty_returns_hint(env) -> None:
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 正文", "p")
    r = client.post("/api/jobs/job1/question",
                    json={"question": "   "}, headers={"X-Owner": "alice"})
    assert "问题为空" in r.json()["answer"]
