"""
Password hashing and JWT issue/verify.

WHY bcrypt DIRECTLY AND NOT passlib
-----------------------------------
passlib is the usual tutorial answer, but it is unmaintained and its bcrypt
backend breaks against bcrypt 4.x. Two functions is not enough code to justify
a dependency that logs errors on import.

WHY THE SHA-256 PRE-HASH
------------------------
bcrypt silently truncates anything past 72 bytes - two different long
passwords sharing their first 72 bytes would authenticate each other. Hashing
to a fixed-length digest first removes the truncation entirely. base64 is used
because the raw digest can contain a NUL byte, which bcrypt also truncates at.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import get_settings

settings = get_settings()


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def _prepare(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed hash in the database must read as "wrong password",
        # never as a 500 that tells an attacker the account exists.
        return False


PASSWORD_RULES = "At least 8 characters, including one letter and one number."


def password_problems(password: str) -> list[str]:
    """Return a list of reasons this password is not acceptable (empty = fine)."""
    problems: list[str] = []
    if len(password) < 8:
        problems.append("Password must be at least 8 characters.")
    if not any(c.isalpha() for c in password):
        problems.append("Password must contain at least one letter.")
    if not any(c.isdigit() for c in password):
        problems.append("Password must contain at least one number.")
    if password.lower() in {"password", "12345678", "password1", "qwerty123"}:
        problems.append("That password is in every leaked-password list. Pick another.")
    return problems


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


class TokenError(Exception):
    """Raised when a token is missing, expired or tampered with."""


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": "interviewace-ai",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            issuer="interviewace-ai",
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Your session has expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid authentication token.") from exc
