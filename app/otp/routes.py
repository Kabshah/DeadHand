"""app/otp/routes.py — POST /otp/request only (§7).

OTP verification is intentionally NOT here — it is inlined into each action
endpoint (POST /switches, POST /switches/{id}/checkin, POST /switches/{id}/cancel).
This eliminates the race that existed when verify and action were separate calls (§5).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.core.rate_limit import otp_request_rate_limited
from app.db import get_db
from app.otp.service import store_otp, resend_otp
from app.switches.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/otp", tags=["otp"])

_VALID_PURPOSES = {"create_switch"}


class OTPRequestBody(BaseModel):
    purpose: str
    resend: bool = False


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(
    body: OTPRequestBody,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(otp_request_rate_limited("dynamic")),
) -> dict:
    """Request an OTP for a given purpose.

    Rate-limited per user + IP (§6). Enqueues email task asynchronously.
    Returns immediately — the client does not wait for the email.

    Supported purposes:
      - create_switch
      - checkin:{switch_id}
      - cancel:{switch_id}
    """
    purpose = body.purpose.strip()

    # Validate purpose format
    if purpose != "create_switch" and not (
        purpose.startswith("checkin:") or purpose.startswith("cancel:")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid purpose. Must be 'create_switch', 'checkin:{id}', or 'cancel:{id}'",
        )

    # Apply per-purpose rate limit
    from app.core.rate_limit import check_rate_limits, get_client_ip, RateLimitExceeded
    from app.core.config import settings

    ip = get_client_ip(request)
    try:
        check_rate_limits(
            (f"rl:otpreq:user:{user.id}:{purpose}", settings.OTP_REQUEST_LIMIT, settings.OTP_REQUEST_WINDOW_SEC),
            (f"rl:otpreq:ip:{ip}:{purpose}", 10, settings.OTP_REQUEST_WINDOW_SEC),
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(exc.window)},
        ) from exc

    try:
        if body.resend:
            code = await resend_otp(user.id, purpose)
        else:
            code = await store_otp(user.id, purpose)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Enqueue email task (fire and forget — route returns immediately)
    from app.tasks.email_tasks import send_otp_email
    try:
        send_otp_email.delay(user.id, purpose, code)
    except Exception as exc:
        logger.warning("Failed to enqueue send_otp_email task: %s", exc)

    logger.info("OTP requested: user_id=%d purpose=%s", user.id, purpose)
    return {"detail": "OTP sent to your registered email address"}
