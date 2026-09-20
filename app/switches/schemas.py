"""app/switches/schemas.py — Pydantic v2 request/response schemas.

IMPORTANT: Response schemas NEVER include secret_ciphertext (§7, §11).
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateSwitchRequest(BaseModel):
    recipient_email: EmailStr
    interval_hours: float = Field(..., gt=0, le=8760, description="Check-in interval in hours (e.g., 0.33 for 20 min, 1 for 1 hr)")
    secret_message: str = Field(..., min_length=1, max_length=10_000)
    otp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class CheckinRequest(BaseModel):
    otp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class CancelRequest(BaseModel):
    otp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SwitchResponse(BaseModel):
    """Safe switch representation — secret_ciphertext is intentionally omitted."""
    id: int
    user_id: int
    recipient_email: str
    interval_hours: float
    next_deadline: datetime
    status: str
    version: int
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SwitchListResponse(BaseModel):
    switches: list[SwitchResponse]
    total: int
