"""app/core/redis_client.py — Singleton sync Redis client + Lua script loader.

Memurai 8.2.7 (Redis 8.2.7 API) detected:
  - EXPIRE NX   ✅ (>= 7.0)
  - GETDEL      ✅ (>= 6.2)
  - SET NX EX   ✅
  - Lua EVAL    ✅

Lua scripts are still loaded for:
  - fixed_window.lua  → portable rate limiter
  - release_lock.lua  → token-based compare-and-del lock release
"""
import logging
from pathlib import Path

import redis as redis_lib

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis_lib.Redis | None = None

# Lua script handles — registered at startup
FIXED_WINDOW_SCRIPT: redis_lib.client.Script | None = None
RELEASE_LOCK_SCRIPT: redis_lib.client.Script | None = None

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def get_redis() -> redis_lib.Redis:
    """Return the singleton sync Redis client (lazy-init)."""
    global _client
    if _client is None:
        _client = redis_lib.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        logger.info("Redis client initialised at %s", settings.REDIS_URL)
    return _client


def load_lua_scripts() -> None:
    """Register Lua scripts with Redis.

    Safe to call multiple times — idempotent guard at top.
    Called explicitly at FastAPI startup (main.py lifespan) and at
    Celery worker startup (celery_app.py signals).  No longer called
    from get_redis() to avoid the circular-init loop:
      get_redis → load_lua_scripts → get_redis → …
    """
    global FIXED_WINDOW_SCRIPT, RELEASE_LOCK_SCRIPT
    if FIXED_WINDOW_SCRIPT is not None and RELEASE_LOCK_SCRIPT is not None:
        return

    r = get_redis()  # safe — get_redis no longer calls us back

    fw_path = _SCRIPTS_DIR / "fixed_window.lua"
    rl_path = _SCRIPTS_DIR / "release_lock.lua"

    FIXED_WINDOW_SCRIPT = r.register_script(fw_path.read_text())
    RELEASE_LOCK_SCRIPT = r.register_script(rl_path.read_text())
    logger.info("Lua scripts loaded: fixed_window.lua, release_lock.lua")


def check_redis_version() -> str:
    """Return the Redis/Memurai server version string."""
    r = get_redis()
    version: str = r.info("server")["redis_version"]
    logger.info("Redis server version: %s", version)
    return version
