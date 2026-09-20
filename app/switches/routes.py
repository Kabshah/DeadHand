"""app/switches/routes.py — Switch CRUD endpoints with inlined OTP verification (§7).

OTP verification is inlined here — NOT in otp/routes.py.
This eliminates the race that existed when verify and action were separate calls (§5).

Endpoints:
  POST /switches                   create_switch — OTP purpose: "create_switch"
  GET  /switches                   list user's switches
  GET  /switches/{id}              get single switch
  POST /switches/{id}/checkin      checkin — OTP purpose: "checkin:{id}"
  POST /switches/{id}/cancel       cancel  — OTP purpose: "cancel:{id}"
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.core.rate_limit import RateLimitExceeded, check_rate_limits, get_client_ip
from app.core.config import settings
from app.db import get_db
from app.otp.service import log_otp_attempt, verify_otp
from app.switches.models import User
from app.switches.schemas import (
    CancelRequest,
    CheckinRequest,
    CreateSwitchRequest,
    SwitchListResponse,
    SwitchResponse,
)
from app.switches import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/switches", tags=["switches"])


def _enforce_otp_verify_limits(request: Request, user: User) -> None:
    """Apply OTP verify rate limits before doing any verification (§6)."""
    ip = get_client_ip(request)
    try:
        check_rate_limits(
            (f"rl:otpver:user:{user.id}", settings.OTP_VERIFY_ATTEMPT_LIMIT, settings.OTP_REQUEST_WINDOW_SEC),
            (f"rl:otpver:ip:{ip}", 20, settings.OTP_REQUEST_WINDOW_SEC),
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP attempts",
            headers={"Retry-After": str(exc.window)},
        ) from exc


async def _verify_otp_or_raise(
    db: AsyncSession,
    request: Request,
    user: User,
    purpose: str,
    code: str,
) -> None:
    """Verify OTP inline. On failure: log attempt with IP, raise 401 with generic message."""
    _enforce_otp_verify_limits(request, user)

    ip = get_client_ip(request)
    success = verify_otp(user.id, purpose, code)
    await log_otp_attempt(db, user.id, purpose, success, ip_address=ip)

    if not success:
        # Generic error — don't reveal "wrong code" vs "expired" (§5, §11)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OTP verification failed",
        )



# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED, response_model=SwitchResponse)
async def create_switch(
    body: CreateSwitchRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SwitchResponse:
    """Create a new Dead Man's Switch. OTP verification inlined (purpose: create_switch)."""
    logger.info("Create Switch attempt: user_id=%d recipient=%s interval=%dhrs", user.id, body.recipient_email, body.interval_hours)
    await _verify_otp_or_raise(db, request, user, "create_switch", body.otp_code)

    try:
        switch = await service.create_switch(
            db=db,
            user_id=user.id,
            recipient_email=str(body.recipient_email),
            interval_hours=body.interval_hours,
            secret_message=body.secret_message,
        )
    except ValueError as exc:
        logger.warning("Create Switch failed: user_id=%d reason=%s", user.id, exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    logger.info("Switch successfully created: switch_id=%d user_id=%d deadline=%s", switch.id, user.id, switch.next_deadline)
    return SwitchResponse.model_validate(switch)


@router.get("", response_model=SwitchListResponse)
async def list_switches(
    q: str | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SwitchListResponse:
    """List all switches for the authenticated user. Never returns secret_ciphertext."""
    logger.info("Listing switches for user_id=%d query=%s", user.id, q)
    switches = await service.get_user_switches(db, user.id, search=q)
    logger.info("Found %d switches for user_id=%d", len(switches), user.id)
    return SwitchListResponse(
        switches=[SwitchResponse.model_validate(s) for s in switches],
        total=len(switches),
    )


@router.get("/{switch_id}", response_model=SwitchResponse)
async def get_switch(
    switch_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SwitchResponse:
    """Get a single switch by ID (must belong to the authenticated user)."""
    logger.info("Fetching switch details: switch_id=%d user_id=%d", switch_id, user.id)
    try:
        switch = await service.get_switch(db, switch_id, user.id)
    except LookupError as exc:
        logger.warning("Switch not found: switch_id=%d user_id=%d", switch_id, user.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SwitchResponse.model_validate(switch)


@router.post("/{switch_id}/checkin", response_model=SwitchResponse)
async def checkin(
    switch_id: int,
    body: CheckinRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SwitchResponse:
    """Check in to extend the deadline. OTP purpose: checkin:{switch_id}."""
    logger.info("Check-in attempt: switch_id=%d user_id=%d", switch_id, user.id)
    purpose = f"checkin:{switch_id}"
    await _verify_otp_or_raise(db, request, user, purpose, body.otp_code)

    try:
        switch = await service.checkin_switch(db, switch_id, user.id)
    except LookupError as exc:
        logger.warning("Check-in failed (not found): switch_id=%d user_id=%d", switch_id, user.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Check-in failed (invalid state): switch_id=%d user_id=%d reason=%s", switch_id, user.id, exc)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    logger.info("Check-in successful: switch_id=%d user_id=%d new_deadline=%s", switch.id, user.id, switch.next_deadline)
    return SwitchResponse.model_validate(switch)


@router.post("/{switch_id}/cancel", response_model=SwitchResponse)
async def cancel(
    switch_id: int,
    body: CancelRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SwitchResponse:
    """Cancel a switch. OTP purpose: cancel:{switch_id}."""
    logger.info("Cancel switch attempt: switch_id=%d user_id=%d", switch_id, user.id)
    purpose = f"cancel:{switch_id}"
    await _verify_otp_or_raise(db, request, user, purpose, body.otp_code)

    try:
        switch = await service.cancel_switch(db, switch_id, user.id)
    except LookupError as exc:
        logger.warning("Cancel switch failed (not found): switch_id=%d user_id=%d", switch_id, user.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Cancel switch failed (invalid state): switch_id=%d user_id=%d reason=%s", switch_id, user.id, exc)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    logger.info("Switch cancelled successfully: switch_id=%d user_id=%d status=%s", switch.id, user.id, switch.status)
    return SwitchResponse.model_validate(switch)
