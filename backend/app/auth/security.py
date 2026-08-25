"""Password hashing and JWT issue/verify.

Uses `bcrypt` directly rather than `passlib`. Passlib has been effectively unmaintained
since 2020 and its bcrypt backend breaks against bcrypt 4.x with a misleading
"password cannot be longer than 72 bytes" error on short passwords. One less dependency
between us and a security primitive is the right trade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

# bcrypt hashes at most 72 bytes and silently ignores the rest. Truncating explicitly
# means a 200-character passphrase and its 72-byte prefix are known to be equivalent,
# rather than that being a surprise discovered during an incident.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash.

    Returns False on a malformed hash rather than raising: an unparseable stored hash
    is a failed authentication, not a server error, and raising here would let a
    corrupted row turn a login attempt into a 500.
    """
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


class TokenError(Exception):
    """Raised when a token is absent, malformed, or expired."""


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Issue a bearer token.

    The role is embedded so the API layer can reject an unauthorised request without a
    database round trip. It is never trusted for approval: `state_machine.approve`
    re-reads the persisted `User` and re-checks the role there, because a token issued
    before a role change would otherwise carry stale authority into the one decision
    where that matters most.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError("Your session is not valid. Please sign in again.") from exc
