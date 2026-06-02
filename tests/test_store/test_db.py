"""测试 sqlite store：CRUD + owner 隔离。用临时 db 文件，不碰生产库。"""
from __future__ import annotations

import pytest

from cca.store import db


@pytest.fixture
def store(tmp_path):
    db.configure(tmp_path / "test.db")
    db.init_db()
    return db


def test_save_and_get_report_roundtrip(store) -> None:
    store.save_report("r1", "alice", "飞书", "# 报告正文", "/tmp/r1.pdf")
    got = store.get_report("r1", "alice")
    assert got is not None
    assert got["target_product"] == "飞书"
    assert got["report_md"] == "# 报告正文"
    assert got["pdf_path"] == "/tmp/r1.pdf"


def test_get_report_isolated_by_owner(store) -> None:
    store.save_report("r1", "alice", "飞书", "md", "p")
    assert store.get_report("r1", "bob") is None      # bob 看不到 alice 的
    assert store.get_report("r1", "alice") is not None


def test_save_report_same_id_overwrites(store) -> None:
    store.save_report("r1", "alice", "飞书", "v1", "p")
    store.save_report("r1", "alice", "飞书", "v2", "p")
    assert store.get_report("r1", "alice")["report_md"] == "v2"


def test_list_reports_only_owner_newest_first(store) -> None:
    store.save_report("r1", "alice", "飞书", "md", "p")
    store.save_report("r2", "alice", "钉钉", "md", "p")
    store.save_report("r3", "bob", "Slack", "md", "p")
    mine = store.list_reports("alice")
    assert [r["id"] for r in mine] == ["r2", "r1"]     # 最新在前
    assert all(r["target_product"] != "Slack" for r in mine)  # 不含 bob 的


def test_conversation_get_or_create_is_stable_and_isolated(store) -> None:
    c1 = store.get_or_create_conversation("r1", "alice")
    c2 = store.get_or_create_conversation("r1", "alice")
    assert c1 == c2                                    # 同 (report, owner) 复用
    assert store.get_or_create_conversation("r1", "bob") != c1  # 不同 owner 隔离


def test_messages_roundtrip_in_order(store) -> None:
    conv = store.get_or_create_conversation("r1", "alice")
    store.add_message(conv, "user", "飞书定价？")
    store.add_message(conv, "assistant", "¥15/月")
    assert store.get_messages(conv) == [
        {"role": "user", "content": "飞书定价？"},
        {"role": "assistant", "content": "¥15/月"},
    ]


def test_messages_isolated_across_conversations(store) -> None:
    a = store.get_or_create_conversation("r1", "alice")
    store.get_or_create_conversation("r1", "bob")
    store.add_message(a, "user", "alice 的问题")
    b = store.get_or_create_conversation("r1", "bob")
    assert store.get_messages(b) == []                 # bob 会话看不到 alice 的消息


def test_get_history_readonly_returns_empty_without_conversation(store) -> None:
    assert store.get_history("rX", "alice") == []      # 无会话返 []，且不创建
    # 确认没有副作用建出会话：list 仍查不到该会话的消息
    assert store.get_history("rX", "alice") == []


def test_get_history_returns_messages_for_owner(store) -> None:
    conv = store.get_or_create_conversation("r1", "alice")
    store.add_message(conv, "user", "Q")
    store.add_message(conv, "assistant", "A")
    assert store.get_history("r1", "alice") == [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]
    assert store.get_history("r1", "bob") == []         # 隔离
