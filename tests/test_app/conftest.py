"""tests/test_app 共享 fixture：临时 db + patch get_report_llm + TestClient，不调真 API。"""
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
    """返回 (TestClient, db)，db 指向本测试独享的临时库。"""
    from cca.store import db
    db.configure(tmp_path / "t.db")
    db.init_db()
    import app.server as server
    monkeypatch.setattr(server, "get_report_llm", _fake_get_report_llm)
    return TestClient(server.app), db
