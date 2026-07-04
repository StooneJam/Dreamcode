"""Shared fixtures for tests/test_app: a temp db + patched get_report_llm + TestClient, no real API calls."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # makes the `app` package importable


def _fake_get_report_llm():
    """A fake ChatModel: echoes back the last HumanMessage, making it easy to assert on grounding and history."""
    def _invoke(messages):
        human = [m for m in messages if type(m).__name__ == "HumanMessage"]
        return SimpleNamespace(content=f"answer to: {human[-1].content}")
    return SimpleNamespace(invoke=_invoke)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Returns (TestClient, db), with db pointing at a temp database exclusive to this test."""
    from cca.store import db
    db.configure(tmp_path / "t.db")
    db.init_db()
    import app.server as server
    monkeypatch.setattr(server, "get_report_llm", _fake_get_report_llm)
    return TestClient(server.app), db


@pytest.fixture
def auth():
    """Factory: creates a session for an owner, returning an Authorization header (Bearer token) per the new auth contract.

    Owner resolution has moved from the X-Owner header to an Authorization session token (see server._resolve_owner).
    """
    def _make(owner: str) -> dict:
        from cca.auth.session import create_session
        return {"Authorization": f"Bearer {create_session(owner)}"}
    return _make
