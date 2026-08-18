"""Password hashing.

Uses bcrypt directly rather than passlib, which is unmaintained and
incompatible with bcrypt >= 4.1. Bcrypt silently truncates input beyond
72 bytes, so we pre-hash with SHA-256 to support arbitrarily long
passwords without losing entropy.
"""
import base64
import hashlib

import bcrypt

MIN_PASSWORD_LENGTH = 8


def _prepare(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    """Constant-time verification that never raises on malformed input."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
