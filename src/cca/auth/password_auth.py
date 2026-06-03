from __future__ import annotations

import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return (salt + key).hex()


def verify_password(password: str, stored: str) -> bool:
    data = bytes.fromhex(stored)
    salt, stored_key = data[:16], data[16:]
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return hmac.compare_digest(key, stored_key)
