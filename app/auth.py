"""Password hashing, session cookies and CSRF tokens.

We avoid external password libraries: scrypt is in the standard library
(``hashlib.scrypt``) and gives a strong, memory-hard KDF out of the box.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from .config import ADMIN_COOKIE_MAX_AGE, ADMIN_COOKIE_NAME, CSRF_TOKEN_LENGTH


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """Return (pw_hash_b64, salt_b64)."""
    if salt is None:
        salt = os.urandom(16)
    # 2**14 = 16384 iterations, r=8, p=1 -> good balance of speed/memory.
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return base64.b64encode(key).decode("ascii"), base64.b64encode(salt).decode("ascii")


def verify_password(password: str, pw_hash: str, salt_b64: str) -> bool:
    salt = base64.b64decode(salt_b64)
    expected = base64.b64encode(
        hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    ).decode("ascii")
    return hmac.compare_digest(expected, pw_hash)


def make_csrf_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def cookie_signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_cookie(payload: str, secret: str) -> str:
    sig = cookie_signature(payload, secret)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii") + "." + sig


def verify_cookie(token: str, secret: str, max_age: int) -> Optional[str]:
    """Return the decoded payload if the signature is valid and not expired."""
    try:
        raw, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    payload_bytes = base64.urlsafe_b64decode(raw)
    expected = cookie_signature(payload_bytes.decode("utf-8"), secret)
    if not hmac.compare_digest(expected, sig):
        return None
    payload = payload_bytes.decode("utf-8")
    # payload is "username|timestamp"
    try:
        username, ts_s = payload.split("|", 1)
        ts = int(ts_s)
    except (ValueError, IndexError):
        return None
    if abs(time.time() - ts) > max_age:
        return None
    return username


def get_secret() -> str:
    """A per-process secret, persisted in DB so cookies survive reloads."""
    secret = os.environ.get("ADMIN_SECRET")
    if secret:
        return secret
    try:
        from .db import db
        row = db.fetchone("SELECT value FROM meta WHERE key='admin_secret'")
        if row:
            return row["value"]
        new = secrets.token_urlsafe(32)
        db.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('admin_secret', ?)", (new,)
        )
        db._conn().commit()
        return new
    except Exception:
        return secrets.token_urlsafe(32)