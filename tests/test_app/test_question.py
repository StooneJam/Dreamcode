"""测试 /api/jobs/{id}/question 的 DB 持久化 + owner 隔离（fixture 见 conftest）。"""
from __future__ import annotations


def test_question_persists_history_and_grounds(env, auth) -> None:
    client, db = env
    alice = auth("alice")
    db.save_report("job1", "alice", "飞书", "# 飞书报告正文", "p.pdf")

    r1 = client.post("/api/jobs/job1/question",
                     json={"question": "定价多少?"}, headers=alice)
    assert r1.status_code == 200
    assert "定价多少?" in r1.json()["answer"]          # 本轮问题进了上下文

    client.post("/api/jobs/job1/question",
                json={"question": "那钉钉?"}, headers=alice)
    conv = db.get_or_create_conversation("job1", "alice")
    msgs = db.get_messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "定价多少?"            # 两轮都落库


def test_question_owner_isolation(env, auth) -> None:
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 正文", "p")
    r = client.post("/api/jobs/job1/question",
                    json={"question": "x"}, headers=auth("bob"))
    assert "无权访问" in r.json()["answer"]            # bob 访问不到 alice 的报告


def test_question_empty_returns_hint(env, auth) -> None:
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 正文", "p")
    r = client.post("/api/jobs/job1/question",
                    json={"question": "   "}, headers=auth("alice"))
    assert "问题为空" in r.json()["answer"]


def test_question_accepts_browser_keys_in_body(env, auth) -> None:
    """请求携带浏览器 key（支持重启后回看再答疑）时仍正常作答，不破路径。"""
    client, db = env
    db.save_report("job1", "alice", "飞书", "# 正文", "p")
    r = client.post("/api/jobs/job1/question",
                    json={"question": "Q", "doubao_key": "sk-test"},
                    headers=auth("alice"))
    assert r.status_code == 200
    assert r.json()["answer"]
