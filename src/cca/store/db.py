"""sqlite persistence for reports and Q&A conversations. All reads/writes are
isolated by owner (username).

Each operation opens a short-lived connection and closes it when done, to avoid
sharing a connection across threads (the server runs the graph in a thread pool).
API keys are never persisted -- only reports and conversations are.
"""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(
    __import__("os").getenv("DB_PATH", "")
    or Path(__file__).resolve().parents[3] / "data" / "cca.db"
)

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
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_identities (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    provider    TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(provider, provider_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS otp_codes (
    phone      TEXT PRIMARY KEY,
    code       TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_traces (
    run_id           TEXT PRIMARY KEY,
    owner            TEXT NOT NULL,
    langsmith_run_id TEXT,
    events_json      TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_owner ON reports(owner, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_lookup ON conversations(report_id, owner);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def configure(path: str | Path) -> None:
    """Switch the db file path (used by tests for a temporary db)."""
    global _DB_PATH
    _DB_PATH = Path(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _tx() -> Iterator[sqlite3.Connection]:
    """A single connection: transaction auto-commits/rolls back, then closes."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create tables (idempotent). Called once at server startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _tx() as conn:
        conn.executescript(_SCHEMA)
        # migration: add the password_hash column (ignored if it already exists)
        try:
            conn.execute("ALTER TABLE user_identities ADD COLUMN password_hash TEXT")
        except sqlite3.OperationalError:
            pass


def save_report(
    report_id: str, owner: str, target_product: str, report_md: str, pdf_path: str
) -> None:
    """Persist a report (same id overwrites)."""
    with _tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reports"
            "(id, owner, target_product, report_md, pdf_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (report_id, owner, target_product, report_md, pdf_path, _now()),
        )


def get_report(report_id: str, owner: str) -> dict | None:
    """Get a report; returns None if owner doesn't match (isolation)."""
    with _tx() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND owner = ?", (report_id, owner)
        ).fetchone()
    return dict(row) if row else None


def list_reports(owner: str) -> list[dict]:
    """This owner's report list, newest first (excludes report_md body to save bandwidth)."""
    with _tx() as conn:
        rows = conn.execute(
            "SELECT id, target_product, pdf_path, created_at FROM reports "
            "WHERE owner = ? ORDER BY created_at DESC, rowid DESC",
            (owner,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_or_create_conversation(report_id: str, owner: str) -> str:
    """Get the conversation id for (report, owner), creating one if none exists."""
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
    """Append one conversation message."""
    with _tx() as conn:
        conn.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, _now()),
        )


def get_messages(conversation_id: str) -> list[dict]:
    """Get a conversation's messages in chronological order: [{role, content}]."""
    with _tx() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def save_run_trace(
    run_id: str, owner: str, langsmith_run_id: str | None, events_json: str
) -> None:
    """Persist a run's agent process event stream (same run_id overwrites). events_json is a JSON array string."""
    with _tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO run_traces"
            "(run_id, owner, langsmith_run_id, events_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, owner, langsmith_run_id, events_json, _now()),
        )


def get_run_trace(run_id: str, owner: str) -> dict | None:
    """Get a run's process event stream; returns None if owner doesn't match (isolation)."""
    with _tx() as conn:
        row = conn.execute(
            "SELECT * FROM run_traces WHERE run_id = ? AND owner = ?", (run_id, owner)
        ).fetchone()
    return dict(row) if row else None


def get_history(report_id: str, owner: str) -> list[dict]:
    """Get all messages for (report, owner); returns [] if no conversation exists (read-only, doesn't create one)."""
    with _tx() as conn:
        conv = conn.execute(
            "SELECT id FROM conversations WHERE report_id = ? AND owner = ?",
            (report_id, owner),
        ).fetchone()
        if not conv:
            return []
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conv["id"],),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ── Auth ──────────────────────────────────────────────────────────────────


def get_or_create_user(provider: str, provider_id: str, display_name: str) -> tuple[str, str]:
    """Look up or create a user by (provider, provider_id), returns (user_id, display_name)."""
    with _tx() as conn:
        row = conn.execute(
            "SELECT user_id FROM user_identities WHERE provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
        if row:
            user_id = row["user_id"]
            name_row = conn.execute(
                "SELECT display_name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return user_id, name_row["display_name"]
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users(id, display_name, created_at) VALUES (?, ?, ?)",
            (user_id, display_name, _now()),
        )
        conn.execute(
            "INSERT INTO user_identities(id, user_id, provider, provider_id, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, provider, provider_id, _now()),
        )
    return user_id, display_name


def create_password_user(username: str, password_hash: str) -> tuple[str, str]:
    """Create a username+password account; raises ValueError if the username is taken."""
    with _tx() as conn:
        if conn.execute(
            "SELECT id FROM user_identities WHERE provider = 'password' AND provider_id = ?",
            (username,),
        ).fetchone():
            raise ValueError("username_taken")
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users(id, display_name, created_at) VALUES (?, ?, ?)",
            (user_id, username, _now()),
        )
        conn.execute(
            "INSERT INTO user_identities"
            "(id, user_id, provider, provider_id, password_hash, created_at)"
            " VALUES (?, ?, 'password', ?, ?, ?)",
            (str(uuid.uuid4()), user_id, username, password_hash, _now()),
        )
    return user_id, username


def get_password_user(username: str) -> tuple[str, str, str] | None:
    """Look up an account by username, returns (user_id, display_name, password_hash) or None."""
    with _tx() as conn:
        row = conn.execute(
            "SELECT ui.user_id, u.display_name, ui.password_hash "
            "FROM user_identities ui JOIN users u ON u.id = ui.user_id "
            "WHERE ui.provider = 'password' AND ui.provider_id = ?",
            (username,),
        ).fetchone()
    return (row["user_id"], row["display_name"], row["password_hash"]) if row else None


def save_session(token: str, user_id: str, expires_at: str) -> None:
    with _tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions(token, user_id, expires_at, created_at)"
            " VALUES (?, ?, ?, ?)",
            (token, user_id, expires_at, _now()),
        )


def get_session_user(token: str) -> str | None:
    with _tx() as conn:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?",
            (token, _now()),
        ).fetchone()
    return row["user_id"] if row else None


def delete_session(token: str) -> None:
    with _tx() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def save_otp(phone: str, code: str, expires_at: str) -> None:
    with _tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO otp_codes(phone, code, expires_at) VALUES (?, ?, ?)",
            (phone, code, expires_at),
        )


def check_and_consume_otp(phone: str, code: str) -> bool:
    """Verify the OTP is correct and unexpired; deletes it immediately on success (prevents replay)."""
    with _tx() as conn:
        row = conn.execute(
            "SELECT code FROM otp_codes WHERE phone = ? AND expires_at > ?",
            (phone, _now()),
        ).fetchone()
        if not row or row["code"] != code:
            return False
        conn.execute("DELETE FROM otp_codes WHERE phone = ?", (phone,))
    return True
