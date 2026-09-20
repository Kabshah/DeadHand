"""app/auth/jwt.py — JWT access tokens + Redis-backed refresh tokens.

Token design (§4):
  - Access token: short-lived (15 min), JWT signed with JWT_SECRET.
  - Refresh token: long-lived, stored as a hashed value in Redis with TTL.
    Only the hash is stored — the raw token is only sent to the client once.
  - Rotation: on refresh, old token is consumed (deleted), new pair issued.
  - Revocation: logout deletes the refresh token from Redis.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_REFRESH_TOKEN_PREFIX = "refresh:"


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    """Issue a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TTL_MIN)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> int:
    """Verify JWT and return user_id. Raises ValueError on invalid/expired token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id = payload.get("sub")
        if user_id is None:
            raise ValueError("Token has no sub claim")
        return int(user_id)
    except JWTError as exc:
        raise ValueError(f"Invalid access token: {exc}") from exc


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    """SHA-256 hash of the raw refresh token (only hash stored in Redis)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _refresh_key(token_hash: str) -> str:
    return f"{_REFRESH_TOKEN_PREFIX}{token_hash}"


def create_refresh_token(user_id: int) -> str:
    """Issue a long-lived refresh token and store its hash in Redis."""
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)
    r = get_redis()
    ttl = settings.JWT_REFRESH_TTL_DAYS * 86400
    r.set(_refresh_key(token_hash), str(user_id), ex=ttl)
    logger.debug("Refresh token created for user_id=%d", user_id)
    return raw


def rotate_refresh_token(old_raw: str) -> tuple[str, str]:
    """Consume old refresh token, issue new access + refresh pair.

    Returns:
        (new_access_token, new_refresh_token)

    Raises:
        ValueError if old token is invalid or already consumed.
    """
    r = get_redis()
    old_hash = _hash_token(old_raw)
    key = _refresh_key(old_hash)

    # Atomically consume the old token
    user_id_str: str | None = r.getdel(key)
    if user_id_str is None:
        raise ValueError("Refresh token is invalid or already consumed")

    user_id = int(user_id_str)
    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    logger.info("Refresh token rotated for user_id=%d", user_id)
    return new_access, new_refresh


def revoke_refresh_token(raw: str) -> None:
    """Delete the refresh token from Redis (logout)."""
    r = get_redis()
    token_hash = _hash_token(raw)
    r.delete(_refresh_key(token_hash))
    logger.info("Refresh token revoked")
