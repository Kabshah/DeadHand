"""app/otp/service.py — OTP generation, storage, and atomic verification (§5).

Security design:
  - Code generated with Python's `secrets` module (CSPRNG) — NOT random.choices (§5).
  - Code stored as sha256(code + user_id + purpose) — never raw code in Redis.
  - NX flag on SET: prevents silent overwrite of in-flight code.
  - Atomic GETDEL consumption: stops double-use race (§10.2).
  - hmac.compare_digest: constant-time comparison, prevents timing attacks (§5).
  - Purpose-scoped key: otp:{user_id}:{purpose} — prevents cross-purpose replay (§5).
  - Generic error on failure: don't reveal "wrong code" vs "expired" (§5, §11).

Brute-force lockout (§5):
  - Consecutive failure counter: otp:failcnt:{user_id}:{purpose}
  - After OTP_MAX_FAIL_ATTEMPTS consecutive wrong guesses:
      - OTP key is deleted (no further guesses accepted)
      - Lockout key set: otp:locked:{user_id}:{purpose} with OTP_LOCKOUT_SECONDS TTL
  - verify_otp() checks lockout key BEFORE consuming the OTP.
  - On success: failure counter is deleted.

Resend cooldown (§5):
  - After issuing any OTP (initial or resend), a cooldown key is set:
      otp:cooldown:{user_id}:{purpose}  TTL = OTP_RESEND_COOLDOWN_SECONDS
  - resend_otp() raises ValueError if the cooldown key is still present,
    including the remaining seconds so the caller can relay them to the user.
  - Initial store_otp() does NOT enforce cooldown — only resend does.

Audit log (§11):
  - log_otp_attempt() writes to the otp_attempts DB table with ip_address.
  - Never log raw OTP codes (§11).
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import get_redis
from app.switches.models import OTPAttempt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

def _otp_key(user_id: int, purpose: str) -> str:
    """Primary OTP hash storage key."""
    return f"otp:{user_id}:{purpose}"


def _lockout_key(user_id: int, purpose: str) -> str:
    """Set when the user is locked out due to too many failed attempts."""
    return f"otp:locked:{user_id}:{purpose}"


def _failcnt_key(user_id: int, purpose: str) -> str:
    """Tracks consecutive failed verification attempts for brute-force detection."""
    return f"otp:failcnt:{user_id}:{purpose}"


def _cooldown_key(user_id: int, purpose: str) -> str:
    """Prevents rapid resend requests (spam / email quota abuse)."""
    return f"otp:cooldown:{user_id}:{purpose}"


# ---------------------------------------------------------------------------
# Core generation + hashing
# ---------------------------------------------------------------------------

def generate_otp_code() -> str:
    """Return a cryptographically secure random 6-digit OTP code.

    Uses Python's built-in `secrets` module (CSPRNG) as recommended
    by NIST SP 800-63B — NOT random.choices which uses the Mersenne Twister
    PRNG and is NOT suitable for security-sensitive values (§5).
    """
    return "".join([str(secrets.randbelow(10)) for _ in range(6)])


def _hash_otp(code: str, user_id: int, purpose: str) -> str:
    """Hash the OTP code with user_id and purpose binding (§5).

    Binding prevents a valid hash for one purpose being replayed
    against a different purpose (cross-purpose replay attack).
    """
    payload = f"{code}:{user_id}:{purpose}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Store / Resend
# ---------------------------------------------------------------------------

async def store_otp(user_id: int, purpose: str) -> str:
    """Generate and store a new OTP. Returns the raw code (to be emailed).

    - Checks for active lockout before generating.
    - Uses NX so a resend does NOT silently overwrite an in-flight code.
    - Sets a cooldown key so the resend path cannot be abused immediately.
    - If the key already exists, raises ValueError — client should wait or
      use an explicit resend path.

    Does NOT enforce cooldown on initial request (only resend does).
    """
    r = get_redis()

    # Block if user is locked out for this purpose
    if r.exists(_lockout_key(user_id, purpose)):
        ttl = r.ttl(_lockout_key(user_id, purpose))
        raise ValueError(
            f"OTP issuance locked due to too many failed attempts. "
            f"Try again in {max(ttl, 1)} second(s)."
        )

    code = generate_otp_code()
    key = _otp_key(user_id, purpose)
    stored_hash = _hash_otp(code, user_id, purpose)

    # NX = only set if key does NOT already exist
    ok: bool = bool(r.set(key, stored_hash, ex=settings.OTP_TTL_SECONDS, nx=True))
    if not ok:
        raise ValueError(
            "OTP already pending for this user+purpose. "
            "Wait for it to expire or request a resend."
        )

    # Set cooldown key so resend cannot fire immediately (NX: don't reset if already set)
    r.set(_cooldown_key(user_id, purpose), "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS, nx=True)

    # NEVER log the raw code (§11)
    logger.info("OTP stored for user_id=%d purpose=%s (code not logged)", user_id, purpose)
    return code


async def resend_otp(user_id: int, purpose: str) -> str:
    """Delete existing OTP and issue a fresh one (explicit resend path).

    Enforces a cooldown: if a code was issued within the last
    OTP_RESEND_COOLDOWN_SECONDS seconds, raises ValueError with remaining wait.
    After issuing, resets the cooldown clock.
    """
    r = get_redis()

    # Enforce resend cooldown — TTL > 0 means cooldown is active
    cooldown_ttl = r.ttl(_cooldown_key(user_id, purpose))
    if cooldown_ttl > 0:
        raise ValueError(
            f"Resend cooldown active. Please wait {cooldown_ttl} more second(s) "
            f"before requesting a new code."
        )

    # Delete the old OTP (if any) so store_otp NX check passes
    r.delete(_otp_key(user_id, purpose))

    code = await store_otp(user_id, purpose)

    # Reset cooldown for this new resend (overwrite, not NX)
    r.set(_cooldown_key(user_id, purpose), "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS)

    logger.info("OTP resent for user_id=%d purpose=%s", user_id, purpose)
    return code


# ---------------------------------------------------------------------------
# Verify (atomic + brute-force aware)
# ---------------------------------------------------------------------------

def verify_otp(user_id: int, purpose: str, code: str) -> bool:
    """Atomically consume and verify the OTP. Returns True on success.

    Security properties:
    - Checks lockout key FIRST — locked users get an immediate False
      without consuming the OTP (lockout is not bypassable).
    - Uses GETDEL so only the first of two concurrent requests with the
      same valid code succeeds (§10.2). hmac.compare_digest prevents timing attacks.
    - On wrong code: increments consecutive-failure counter. If counter
      reaches OTP_MAX_FAIL_ATTEMPTS, sets the lockout key.
    - On success: clears the failure counter.
    - On any failure (wrong code, expired, already consumed, locked),
      returns False. Never reveals which failure mode (§5, §11).
    """
    r = get_redis()

    # 1. Check lockout BEFORE consuming the OTP key
    if r.exists(_lockout_key(user_id, purpose)):
        ttl = r.ttl(_lockout_key(user_id, purpose))
        logger.warning(
            "OTP verify blocked (locked out) user_id=%d purpose=%s ttl=%d",
            user_id, purpose, ttl,
        )
        return False

    key = _otp_key(user_id, purpose)

    # 2. Atomic get + delete. Only one concurrent caller gets the stored hash.
    stored_hash: str | None = r.getdel(key)
    if stored_hash is None:
        logger.info(
            "OTP verify failed (expired/consumed) user_id=%d purpose=%s",
            user_id, purpose,
        )
        return False

    expected_hash = _hash_otp(code, user_id, purpose)

    # 3. Constant-time comparison — not == (timing attack, §5)
    if not hmac.compare_digest(stored_hash, expected_hash):
        # Wrong code — track consecutive failure
        fail_key = _failcnt_key(user_id, purpose)
        pipe = r.pipeline()
        pipe.incr(fail_key)
        pipe.expire(fail_key, settings.OTP_TTL_SECONDS, nx=True)
        results = pipe.execute()
        fail_count: int = results[0]

        logger.warning(
            "OTP verify failed (wrong code) user_id=%d purpose=%s fail_count=%d",
            user_id, purpose, fail_count,
        )

        if fail_count >= settings.OTP_MAX_FAIL_ATTEMPTS:
            # Activate brute-force lockout
            r.set(_lockout_key(user_id, purpose), "1", ex=settings.OTP_LOCKOUT_SECONDS)
            r.delete(fail_key)  # reset counter after lockout
            logger.warning(
                "OTP brute-force lockout triggered: user_id=%d purpose=%s "
                "lockout_seconds=%d",
                user_id, purpose, settings.OTP_LOCKOUT_SECONDS,
            )

        return False

    # 4. Success — clear the failure counter
    r.delete(_failcnt_key(user_id, purpose))
    logger.info("OTP verified successfully user_id=%d purpose=%s", user_id, purpose)
    return True


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

async def log_otp_attempt(
    db: AsyncSession,
    user_id: int,
    purpose: str,
    success: bool,
    ip_address: str = "unknown",
) -> None:
    """Write an OTPAttempt audit record. Append-only, never update.

    Records ip_address for security monitoring (§11).
    Never call this with the raw OTP code — only metadata.
    """
    attempt = OTPAttempt(
        user_id=user_id,
        purpose=purpose,
        success=success,
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    await db.flush()

