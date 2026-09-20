"""app/core/rate_limit.py — Dual-layer rate limiting (user + IP).

Design (§6):
  - Two layers required: user-based alone is bypassable (multiple accounts, one IP);
    IP-based alone is bypassable (VPN/proxy rotation).
  - Fixed-window via native EXPIRE NX (Memurai >= 7.0 confirmed).
  - Lua path (fixed_window.lua) shipped for portability / tests.
  - Always return 429 with Retry-After header.

Limiter table (§6):
  | Layer                    | Key                                         | Limit | Window  |
  |--------------------------|---------------------------------------------|-------|---------|
  | OTP request — per user   | rl:otpreq:user:{user_id}:{purpose}          | 3     | 10 min  |
  | OTP request — per IP     | rl:otpreq:ip:{ip}:{purpose}                 | 10    | 10 min  |
  | OTP verify  — per user   | rl:otpver:user:{user_id}                    | 5     | 10 min  |
  | OTP verify  — per IP     | rl:otpver:ip:{ip}                           | 20    | 10 min  |
  | Login       — per IP     | rl:login:ip:{ip}                            | 10    | 10 min  |
"""
import logging
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a rate limit window is breached."""

    def __init__(self, key: str, window: int) -> None:
        self.key = key
        self.window = window
        super().__init__(f"Rate limit exceeded: {key}")


def get_client_ip(request: Request) -> str:
    """Return real client IP.

    Trust X-Forwarded-For only when TRUST_PROXY_HEADERS=True (§6).
    Never trust XFF when you don't control the proxy — a client can forge it
    and bypass IP limiting entirely.
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def check_rate_limits(*limiters: tuple[str, int, int]) -> None:
    """Check (key, limit, window_seconds) pairs; raise RateLimitExceeded on first breach.

    Uses native EXPIRE NX pipeline (Memurai >= 7.0).
    If INCR returns a value > limit, the window was already open and this is
    an excess request — raise immediately.
    """
    r = get_redis()
    for key, limit, window in limiters:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)  # NX: set TTL only when key is NEW (§6)
        results = pipe.execute()
        count: int = results[0]
        if count > limit:
            logger.warning("Rate limit breached: key=%s count=%d limit=%d", key, count, limit)
            raise RateLimitExceeded(key=key, window=window)


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------

def otp_request_rate_limited(purpose: str) -> Callable:
    """Return a FastAPI dependency enforcing both user + IP OTP-request limits."""

    async def dep(request: Request) -> None:
        # Lazy import to avoid circular dependency (auth → rate_limit → auth)
        from app.auth.dependencies import current_user as _current_user
        from fastapi import Depends as _Depends
        user = await _resolve_user(request)
        ip = get_client_ip(request)
        try:
            check_rate_limits(
                (f"rl:otpreq:user:{user.id}:{purpose}", settings.OTP_REQUEST_LIMIT, settings.OTP_REQUEST_WINDOW_SEC),
                (f"rl:otpreq:ip:{ip}:{purpose}", 10, settings.OTP_REQUEST_WINDOW_SEC),
            )
        except RateLimitExceeded as exc:
            raise _rate_limit_http_error(exc) from exc

    return dep


def otp_verify_rate_limited() -> Callable:
    """Return a FastAPI dependency enforcing both user + IP OTP-verify limits."""

    async def dep(request: Request) -> None:
        user = await _resolve_user(request)
        ip = get_client_ip(request)
        try:
            check_rate_limits(
                (f"rl:otpver:user:{user.id}", settings.OTP_VERIFY_ATTEMPT_LIMIT, settings.OTP_REQUEST_WINDOW_SEC),
                (f"rl:otpver:ip:{ip}", 20, settings.OTP_REQUEST_WINDOW_SEC),
            )
        except RateLimitExceeded as exc:
            raise _rate_limit_http_error(exc) from exc

    return dep


def login_rate_limited() -> Callable:
    """Return a FastAPI dependency enforcing login-per-IP limits."""

    async def dep(request: Request) -> None:
        ip = get_client_ip(request)
        try:
            check_rate_limits(
                (f"rl:login:ip:{ip}", settings.LOGIN_LIMIT_PER_IP, settings.LOGIN_WINDOW_SEC),
            )
        except RateLimitExceeded as exc:
            raise _rate_limit_http_error(exc) from exc

    return dep


def _rate_limit_http_error(exc: RateLimitExceeded) -> HTTPException:
    """Convert RateLimitExceeded into a 429 HTTPException with Retry-After header."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
        headers={"Retry-After": str(exc.window)},
    )


async def _resolve_user(request: Request):
    """Resolve the current user from the request using Bearer token.

    Deferred import avoids circular dependency between auth.dependencies and rate_limit.
    """
    from app.auth.jwt import verify_access_token
    from app.db import AsyncSessionLocal
    from app.switches.models import User
    from fastapi import HTTPException, status
    from fastapi.security import HTTPBearer
    from sqlalchemy import select

    # Extract Bearer token manually (same logic as dependencies.py)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header[7:]
    try:
        user_id = verify_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
