"""app/auth/routes.py — Auth endpoints (§4, §7).

GET  /auth/login     → redirect to Google
GET  /auth/callback  → CSRF check, exchange code, upsert user, issue tokens
POST /auth/refresh   → rotate refresh token
POST /auth/logout    → revoke refresh token
"""
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.jwt import create_access_token, create_refresh_token, revoke_refresh_token, rotate_refresh_token
from app.auth.oauth import build_google_auth_url, exchange_code_for_profile, generate_oauth_state, upsert_user
from app.core.config import settings
from app.core.rate_limit import login_rate_limited
from app.db import get_db
from app.switches.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class DevLoginRequest(BaseModel):
    email: str = "iamkabshah@gmail.com"


@router.get("/login", dependencies=[Depends(login_rate_limited())])
async def login() -> RedirectResponse:
    """Generate OAuth state (CSRF token), store in Redis, redirect to Google."""
    state = generate_oauth_state()
    url = build_google_auth_url(state)
    logger.info("OAuth login initiated")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth2 callback.

    CSRF state is verified and atomically consumed before anything else.
    This is the #1 OAuth security check — never skip it (§4).
    """
    if not code or not state:
        logger.warning("OAuth callback hit without code/state query parameters, redirecting to frontend")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/", status_code=status.HTTP_302_FOUND)

    from app.auth.oauth import verify_and_consume_state

    if not verify_and_consume_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    try:
        profile = await exchange_code_for_profile(code)
    except Exception as exc:
        logger.exception("Google token exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to complete Google OAuth: {exc}",
        ) from exc

    from app.core.rate_limit import get_client_ip

    client_ip = get_client_ip(request)
    user = await upsert_user(db, profile, client_ip=client_ip)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    logger.info("User authenticated: user_id=%d ip=%s", user.id, client_ip)

    frontend_callback = (
        f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"
        f"#access_token={access_token}&refresh_token={refresh_token}"
    )
    return RedirectResponse(url=frontend_callback, status_code=status.HTTP_302_FOUND)


@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(current_user)) -> UserProfileResponse:
    """Return authenticated user profile."""
    return UserProfileResponse.model_validate(user)


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(
    body: DevLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Development-only instant login helper."""
    if settings.APP_ENV != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login only available in development mode",
        )
    from sqlalchemy import select
    from app.core.rate_limit import get_client_ip

    client_ip = get_client_ip(request)
    email = body.email.strip().lower()

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            google_sub=f"dev_{email}",
            email=email,
            created_ip=client_ip,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    logger.info("Dev login successful for user_id=%d (%s)", user.id, email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh")
async def refresh_tokens(body: RefreshRequest) -> TokenResponse:
    """Rotate refresh token: consume old, issue new access + refresh pair."""
    try:
        new_access, new_refresh = rotate_refresh_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest) -> Response:
    """Revoke the refresh token (delete from Redis)."""
    revoke_refresh_token(body.refresh_token)
    logger.info("User logged out")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
