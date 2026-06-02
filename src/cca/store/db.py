"""报告与 Q&A 对话的 sqlite 持久化。所有读写按 owner（用户名）隔离。

每次操作开一个短连接、用完即关，避免跨线程共享连接（server 在线程池里跑 graph）。
API key 不入库——只持久化报告与对话。
"""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "cca.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id             TEXT PRIMARY KEY,
    owner          TEXT NOT NULL,
    target_product TEXT,
    report_md      TEXT,
    pdf_path       TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    report_id  TEXT NOT NULL,
    owner      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_owner ON reports(owner, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_lookup ON conversations(report_id, owner);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
"""


def configure(path: str | Path) -> None:
    """切换 db 文件路径（测试用临时库）。"""
    global _DB_PATH
    _DB_PATH = Path(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _tx() -> Iterator[sqlite3.Connection]:
    """一次连接：事务自动提交/回滚，用完即关。"""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """建表（幂等）。server 启动时调一次。"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _tx() as conn:
        conn.executescript(_SCHEMA)


def save_report(
    report_id: str, owner: str, target_product: str, report_md: str, pdf_path: str
) -> None:
    """落库一份报告（同 id 覆盖）。"""
    with _tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reports"
            "(id, owner, target_product, report_md, pdf_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (report_id, owner, target_product, report_md, pdf_path, _now()),
        )


def get_report(report_id: str, owner: str) -> dict | None:
    """取报告，owner 不匹配返 None（隔离）。"""
    with _tx() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND owner = ?", (report_id, owner)
        ).fetchone()
    return dict(row) if row else None


def list_reports(owner: str) -> list[dict]:
    """该 owner 的报告列表，最新在前（不含 report_md 正文，省带宽）。"""
    with _tx() as conn:
        rows = conn.execute(
            "SELECT id, target_product, pdf_path, created_at FROM reports "
            "WHERE owner = ? ORDER BY created_at DESC, rowid DESC",
            (owner,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_or_create_conversation(report_id: str, owner: str) -> str:
    """取 (report, owner) 的会话 id，没有则新建。"""
    with _tx() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE report_id = ? AND owner = ?",
            (report_id, owner),
        ).fetchone()
        if row:
            return row["id"]
        conv_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO conversations(id, report_id, owner, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, report_id, owner, _now()),
        )
        return conv_id


def add_message(conversation_id: str, role: str, content: str) -> None:
    """追加一条对话消息。"""
    with _tx() as conn:
        conn.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, _now()),
        )


def get_messages(conversation_id: str) -> list[dict]:
    """按时间顺序取会话消息 [{role, content}]。"""
    with _tx() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]
