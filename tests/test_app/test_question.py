"""测试 /api/jobs/{id}/question 的 DB 持久化 + owner 隔离。patch get_report_llm，不调真 API。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 让 `app` 包可导入


def _fake_get_report_llm():
    """假 ChatModel：回声最后一条 HumanMessage，便于断言 grounding 与历史。"""
    def _invoke(messages):
        human = [m for m in messages if type(m).__name__ == "HumanMessage"]
        return SimpleNamespace(content=f"answer to: {human[-1].content}")
    return SimpleNamespace(invoke=_invoke)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from cca.store import db
    db.configure(tmp_path / "t.db")
    db.init_db()
    import app.server as server
    monkeypatch.setattr(server, "get_report_llm", _fake_get_report_llm)
    return TestClient(server.app), db


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
