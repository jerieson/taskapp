"""Password hashing (argon2 via pwdlib), random tokens and signed values."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

_password_hash = PasswordHash.recommended()

# Verified against when the user does not exist, so a failed login takes the same
# time whether or not the username is known.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except UnknownHashError:  # an unusable placeholder hash never matches
        return False


def burn_password_check(password: str) -> None:
    """Spend the time of one password verification (for unknown users)."""
    _password_hash.verify(password, _DUMMY_HASH)


def generate_token() -> str:
    """URL-safe random token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are random, so a plain SHA-256 is enough; only this hash is stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _signature(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def sign_value(secret: str, data: dict[str, Any], max_age_seconds: int) -> str:
    """Tamper-proof (not encrypted) value for a cookie: payload.signature."""
    payload = _b64(json.dumps({"d": data, "exp": int(time.time()) + max_age_seconds}).encode())
    return f"{payload}.{_signature(secret, payload)}"


def unsign_value(secret: str, value: str | None) -> dict[str, Any] | None:
    """Return the data from `sign_value`, or None if tampered, malformed or expired."""
    if not value or value.count(".") != 1:
        return None
    payload, signature = value.split(".")
    if not hmac.compare_digest(signature, _signature(secret, payload)):
        return None
    try:
        decoded = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(decoded, dict) or decoded.get("exp", 0) < time.time():
        return None
    data = decoded.get("d")
    return data if isinstance(data, dict) else None
