"""app/auth/oauth.py — Google OAuth2 via Authlib (§4).

Flow:
  1. GET /auth/login  → generate state, store in Redis, redirect to Google.
  2. GET /auth/callback → verify + atomically delete state (CSRF), exchange code,
     fetch profile, upsert User by google_sub.

Security: CSRF state check is non-negotiable — skipping it is the #1 OAuth mistake (§4).
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import get_redis
from app.switches.models import User

logger = logging.getLogger(__name__)

_STATE_TTL = 300  # 5 minutes
_STATE_PREFIX = "oauth:state:"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def generate_oauth_state() -> str:
    """Generate a cryptographically random state token and store it in Redis."""
    state = secrets.token_urlsafe(32)
    r = get_redis()
    r.set(f"{_STATE_PREFIX}{state}", "1", ex=_STATE_TTL)
    logger.debug("OAuth state generated and stored in Redis")
    return state


def verify_and_consume_state(state: str) -> bool:
    """Verify state exists in Redis, then atomically delete it (CSRF check).

    Using GETDEL ensures the state can only be consumed once, preventing
    replay attacks. Returns True if valid, False if missing/expired.
    """
    r = get_redis()
    result: str | None = r.getdel(f"{_STATE_PREFIX}{state}")
    if result is None:
        logger.warning("OAuth state verification failed — state missing or expired: %s", state[:8])
        return False
    return True


def build_google_auth_url(state: str) -> str:
    """Return the Google OAuth2 authorization URL."""
    client = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        scope="openid email profile",
    )
    uri, _ = client.create_authorization_url(GOOGLE_AUTHORIZE_URL, state=state)
    return uri


async def exchange_code_for_profile(code: str) -> dict[str, Any]:
    """Exchange authorization code for Google profile dict.

    Returns dict with at minimum: sub, email, name.
    """
    async with AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    ) as client:
        await client.fetch_token(GOOGLE_TOKEN_URL, code=code)
        resp = await client.get(GOOGLE_USERINFO_URL)
        resp.raise_for_status()
        profile: dict[str, Any] = resp.json()
        logger.info("Google OAuth profile fetched for sub=%s", profile.get("sub", "?"))
        return profile


from fastapi import HTTPException, status


async def upsert_user(db: AsyncSession, profile: dict[str, Any], client_ip: str | None = None) -> User:
    """Look up User by google_sub; create if not exists; upsert email on conflict.

    Enforces 1 account per IP policy during new user registration (§4).
    Identity key is google_sub — not email, because Google account emails can
    change. Using email as PK breaks re-login after an email change (§3).
    """
    google_sub: str = profile["sub"]
    email: str = profile.get("email", "")
    now = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user: User | None = result.scalar_one_or_none()

# Jab koi naya user sign-up karta hai (user is None), toh system check karta hai ki incoming client_ip database me users.created_ip me pehle se exist karti hai ya nahi (select(User).where(User.created_ip == client_ip)).
# Agar us IP se pehle hi koi account bana hota hai (existing_ip_user is not None), toh system new registration block karke HTTP 400 Bad Request exception raise karta hai:
# "An account has already been registered from this IP address"

# Agar IP pehli baar aayi hai, toh naya user create ho jata hai aur uski IP (created_ip) DB me save ho jati hai.
# Agar purana user usi IP se dobara log in karega (user is NOT None), toh wo else branch me chala jayega aur uska login normal success hoga!
    if user is None:
        if not client_ip:
            logger.warning("Account creation blocked: client IP address is missing")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client IP address is required for user registration",
            )

        # Enforce 1 account per IP limit for new registrations
        ip_check = await db.execute(select(User).where(User.created_ip == client_ip))
        existing_ip_user = ip_check.scalar_one_or_none()
        if existing_ip_user is not None:
            logger.warning("Account creation blocked (IP limit): ip=%s existing_user_id=%d", client_ip, existing_ip_user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account has already been registered from this IP address",
            )

        user = User(google_sub=google_sub, email=email, created_ip=client_ip, created_at=now)
        db.add(user)
        await db.flush()
        logger.info("New user created: google_sub=%s created_ip=%s", google_sub, client_ip)
    else:
        # Upsert email — it can change on the Google side
        if user.email != email:
            logger.info("Email updated for user_id=%d: %s → %s", user.id, user.email, email)
            user.email = email
        await db.flush()

    return user
