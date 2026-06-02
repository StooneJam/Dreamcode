from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from cca.store import db

_EXPIRY_DAYS = 30


def create_session(user_id: str) -> str:
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)).isoformat()
    db.save_session(token, user_id, expires_at)
    return token


def resolve_session(token: str) -> str | None:
    return db.get_session_user(token)


def delete_session(token: str) -> None:
    db.delete_session(token)
