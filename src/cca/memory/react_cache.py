"""ReAct 节点产出缓存 —— demo 兜底重放用。

缓存粒度：每个 ReAct 节点的 messages list（不是节点返回 dict，因为视觉上想保留流式打印）。
存储：SQLite `react_cache` 表，复用 data/memory/store.db。
key：`{node_name}:{sha256(input_slice)[:16]}`。input_slice 是节点真正消费的状态字段，
变了就不命中——保证 cache 反映上游变化。

模式（环境变量 CCA_CACHE_MODE）：
    off (默认) - 不读不写，每次都真跑
    write     - 真跑后写缓存
    replay    - 强制读缓存，未命中抛错（demo 现场用这个保证秒级）
    auto      - 优先读，未命中真跑 + 写（开发期友好）
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
    """读 CCA_CACHE_MODE；非法值 fallback 到 off + 抛警告打印（不抛异常，避免影响主流程）。"""
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
    """key_data → 稳定 16 hex 摘要。key_data 必须 JSON 可序列化（default=str 兜底非标准类型）。"""
    s = json.dumps(key_data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _full_key(node_name: str, key_data: dict) -> str:
    return f"{node_name}:{hash_key(key_data)}"


def get(node_name: str, key_data: dict) -> dict | None:
    """查缓存。返回 payload dict（不存在时 None）。"""
    key = _full_key(node_name, key_data)
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT payload FROM react_cache WHERE key = ?", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def put(node_name: str, key_data: dict, payload: dict) -> None:
    """写缓存。重复 key 覆盖。"""
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
    """列出所有缓存项摘要（管理用）。返回 [{key, node_name, created_at, size}]。"""
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
    """清空缓存。给定 node_name 则只清该节点；否则清全部。返回删除条数。"""
    with sqlite3.connect(_db_path()) as conn:
        _ensure_table(conn)
        if node_name:
            cur = conn.execute("DELETE FROM react_cache WHERE node_name = ?", (node_name,))
        else:
            cur = conn.execute("DELETE FROM react_cache")
        conn.commit()
        return cur.rowcount
