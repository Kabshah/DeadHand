"""app/core/locks.py — Distributed per-switch locking (§10.3, §10.6).

Uses token-based compare-and-del so a slow task can't accidentally release
another worker's lock after TTL expiry.

Acquire:  SET lock:switch:{id} {random_token} NX EX 30
Release:  Lua compare-and-del (release_lock.lua) — only deletes if token matches
"""
import logging
import secrets

from app.core.redis_client import RELEASE_LOCK_SCRIPT, get_redis

logger = logging.getLogger(__name__)

_LOCK_TTL_SECONDS = 30
_LOCK_KEY_PREFIX = "lock:switch:"


def acquire_lock(switch_id: int) -> str | None:
    """Try to acquire a per-switch distributed lock.

    Returns:
        The lock token (str) if acquired, or None if another worker holds the lock.
    """
    r = get_redis()
    token = secrets.token_hex(16)
    key = f"{_LOCK_KEY_PREFIX}{switch_id}"
    acquired: bool = bool(r.set(key, token, nx=True, ex=_LOCK_TTL_SECONDS))
    if acquired:
        logger.info("Redis Lock ACQUIRED for switch_id=%d (token=%s...)", switch_id, token[:8])
        return token
    logger.info("Redis Lock BUSY for switch_id=%d — held by another worker", switch_id)
    return None


def release_lock(switch_id: int, token: str) -> bool:
    """Release the lock only if we still own it (token matches)."""
    import app.core.redis_client as redis_client

    redis_client.load_lua_scripts()

    if redis_client.RELEASE_LOCK_SCRIPT is None:
        raise RuntimeError("Lua scripts not loaded. Call load_lua_scripts() at startup.")

    key = f"{_LOCK_KEY_PREFIX}{switch_id}"
    result: int = redis_client.RELEASE_LOCK_SCRIPT(keys=[key], args=[token])
    released = bool(result)
    if released:
        logger.info("Redis Lock RELEASED for switch_id=%d", switch_id)
    else:
        logger.warning(
            "Lock release failed for switch_id=%d — token mismatch or already expired", switch_id
        )
    return released
