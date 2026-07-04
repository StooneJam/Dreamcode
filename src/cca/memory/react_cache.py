"""ReAct node output cache -- for demo fallback replay.

Cache granularity: each ReAct node's messages list (not the node's return dict,
since we want to keep the streamed print output).
Storage: SQLite `react_cache` table, reusing data/memory/store.db.
key: `{node_name}:{sha256(input_slice)[:16]}`. input_slice is the state fields the
node actually consumes; if they change, the cache misses -- so it always reflects
upstream changes.

Modes (env var CCA_CACHE_MODE):
    off (default) - no read/write, always runs for real
    write         - runs for real, then writes the cache
    replay        - forces a cache read, raises on miss (use this for demos to guarantee instant results)
    auto          - reads first, falls back to a real run + write on miss (dev-friendly)
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cca.settings import PROJECT_ROOT, load_config

CacheMode = Literal["off", "write", "replay", "auto"]

_VALID_MODES = ("off", "write", "replay", "auto")


def get_mode() -> CacheMode:
    """Read CCA_CACHE_MODE; an invalid value falls back to off + a printed warning
    (never raises, to avoid disrupting the main pipeline)."""
    raw = (os.getenv("CCA_CACHE_MODE") or "off").lower()
    if raw not in _VALID_MODES:
        print(f"  [react_cache] WARN: invalid CCA_CACHE_MODE={raw!r}, fallback to 'off'", flush=True)
        return "off"
    return raw  # type: ignore[return-value]


def _db_path() -> Path:
    raw = load_config().get("paths", {}).get("store_db", "data/memory/store.db")
    p = Path(raw) if Path(raw).is_absolute() else PROJECT_ROOT / raw
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS react_cache (
            key        TEXT PRIMARY KEY,
            node_name  TEXT NOT NULL,
            payload    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()


def hash_key(key_data: dict) -> str:
    """key_data -> a stable 16-hex digest. key_data must be JSON-serializable (default=str covers non-standard types)."""
    s = json.dumps(key_data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _full_key(node_name: str, key_data: dict) -> str:
    return f"{node_name}:{hash_key(key_data)}"


def get(node_name: str, key_data: dict) -> dict | None:
    """Look up the cache. Returns the payload dict, or None if absent."""
    key = _full_key(node_name, key_data)
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT payload FROM react_cache WHERE key = ?", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def put(node_name: str, key_data: dict, payload: dict) -> None:
    """Write the cache. A repeated key overwrites."""
    key = _full_key(node_name, key_data)
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO react_cache (key, node_name, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            (key, node_name,
             json.dumps(payload, ensure_ascii=False, default=str),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def list_entries() -> list[dict]:
    """List a summary of every cache entry (for admin use). Returns [{key, node_name, created_at, size}]."""
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT key, node_name, created_at, length(payload) FROM react_cache "
            "ORDER BY created_at DESC"
        ).fetchall()
    return [
        {"key": k, "node_name": n, "created_at": ts, "size": size}
        for k, n, ts, size in rows
    ]


def clear(node_name: str | None = None) -> int:
    """Clear the cache. If node_name is given, clears only that node; otherwise clears everything. Returns the row count deleted."""
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        if node_name:
            cur = conn.execute("DELETE FROM react_cache WHERE node_name = ?", (node_name,))
        else:
            cur = conn.execute("DELETE FROM react_cache")
        conn.commit()
        return cur.rowcount
