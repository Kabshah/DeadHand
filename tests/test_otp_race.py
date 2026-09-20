"""tests/test_otp_race.py — OTP atomicity, brute-force lockout, and resend cooldown tests (§14).

Existing scenarios (§10.2):
  - Two concurrent requests with the same valid OTP — exactly one must win.
  - Used OTP cannot be reused (GETDEL consumed).
  - Wrong code returns False.
  - Expired OTP returns False.

New scenarios (hardening):
  - generate_otp_code() always returns 6 digits (secrets-based).
  - Brute-force lockout triggers after OTP_MAX_FAIL_ATTEMPTS consecutive failures.
  - Locked user cannot verify even with the correct code.
  - Resend cooldown blocks immediate resend (ValueError raised).
  - Resend succeeds after cooldown expires.
"""
import asyncio
import pytest

import fakeredis
from unittest.mock import patch

from app.otp.service import (
    generate_otp_code,
    store_otp,
    resend_otp,
    verify_otp,
    _lockout_key,
    _failcnt_key,
    _cooldown_key,
)
from app.core.config import settings


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


# Existing race / atomicity tests
@pytest.mark.asyncio
async def test_concurrent_otp_verify_exactly_one_wins(r):
    """
    Simulate two concurrent verify calls with the same valid OTP code.
    Exactly one must return True; the other must return False.
    This proves GETDEL atomicity prevents double-OTP-use (§10.2).
    """
    user_id = 1
    purpose = "create_switch"

    with patch("app.otp.service.get_redis", return_value=r), \
         patch("app.core.redis_client._client", r):

        code = await store_otp(user_id, purpose)

        results = await asyncio.gather(
            asyncio.to_thread(verify_otp, user_id, purpose, code),
            asyncio.to_thread(verify_otp, user_id, purpose, code),
        )

    successes = sum(1 for r in results if r is True)
    failures = sum(1 for r in results if r is False)

    assert successes == 1, f"Expected exactly 1 success, got {successes} (results: {results})"
    assert failures == 1, f"Expected exactly 1 failure, got {failures} (results: {results})"


@pytest.mark.asyncio
async def test_used_otp_cannot_be_reused(r):
    """After a successful verify, the same code cannot be used again."""
    user_id = 2
    purpose = "checkin:99"

    with patch("app.otp.service.get_redis", return_value=r):
        code = await store_otp(user_id, purpose)

        first = verify_otp(user_id, purpose, code)
        assert first is True

        second = verify_otp(user_id, purpose, code)
        assert second is False


@pytest.mark.asyncio
async def test_wrong_code_fails(r):
    """Verify with wrong code returns False."""
    user_id = 3
    purpose = "cancel:5"

    with patch("app.otp.service.get_redis", return_value=r):
        await store_otp(user_id, purpose)
        result = verify_otp(user_id, purpose, "000000")
        assert result is False


@pytest.mark.asyncio
async def test_expired_otp_returns_false(r):
    """If the OTP key doesn't exist (expired/consumed), verify returns False."""
    user_id = 4
    purpose = "create_switch"

    with patch("app.otp.service.get_redis", return_value=r):
        result = verify_otp(user_id, purpose, "123456")
        assert result is False


# New: secrets-based generation

def test_generate_otp_code_is_six_digits():
    """generate_otp_code() must always produce exactly 6 decimal digits."""
    for _ in range(100):
        code = generate_otp_code()
        assert len(code) == 6, f"Expected 6 digits, got {len(code)}: {code!r}"
        assert code.isdigit(), f"Expected all digits, got: {code!r}"


def test_generate_otp_code_uses_secrets():
    """Ensure secrets.randbelow is used in the function body, not random.choices."""
    import app.otp.service as svc
    import ast, inspect, textwrap

    src = inspect.getsource(svc.generate_otp_code)
    # Parse the AST — walk statement nodes to extract non-docstring code
    tree = ast.parse(textwrap.dedent(src))
    func_def = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    # Collect all Call node attribute names
    calls = [
        f"{getattr(n.func, 'value', {type: type(n.func).__name__}).id}.{n.func.attr}"
        for n in ast.walk(func_def)
        if isinstance(n, ast.Call) and isinstance(getattr(n, 'func', None), ast.Attribute)
        and hasattr(getattr(n.func, 'value', None), 'id')
    ]
    assert any("secrets" in c for c in calls), \
        f"generate_otp_code must call a secrets.* function; found calls: {calls}"
    assert not any("random" in c for c in calls), \
        f"generate_otp_code must NOT call random.*; found calls: {calls}"


# New: brute-force lockout
@pytest.mark.asyncio
async def test_brute_force_lockout_triggers_after_max_fails(r):
    """After OTP_MAX_FAIL_ATTEMPTS consecutive wrong guesses, lockout key is set.

    Because GETDEL consumes the OTP key on every wrong attempt, we must
    store a fresh OTP before each failing verify call.
    The failcnt key accumulates across OTP generations for the same purpose.
    """
    user_id = 10
    purpose = "create_switch"
    max_fails = settings.OTP_MAX_FAIL_ATTEMPTS

    with patch("app.otp.service.get_redis", return_value=r):
        for i in range(max_fails):
            # Need a fresh OTP per attempt because GETDEL consumes it
            await store_otp(user_id, purpose)
            result = verify_otp(user_id, purpose, "000000")  # always wrong
            assert result is False

            if i < max_fails - 1:
                # Not yet at the threshold — no lockout
                assert not r.exists(_lockout_key(user_id, purpose)), \
                    f"Should not be locked after {i+1} fail(s) (threshold={max_fails})"

    # After exactly max_fails consecutive fails, lockout must be active
    assert r.exists(_lockout_key(user_id, purpose)), \
        f"Lockout key must be set after {max_fails} consecutive failures"


@pytest.mark.asyncio
async def test_locked_user_cannot_verify(r):
    """A locked user is blocked from verify even with the correct code."""
    user_id = 11
    purpose = "create_switch"

    with patch("app.otp.service.get_redis", return_value=r):
        code = await store_otp(user_id, purpose)

        # Manually set lockout key
        r.set(_lockout_key(user_id, purpose), "1", ex=300)

        result = verify_otp(user_id, purpose, code)
        assert result is False, "Locked user must not be able to verify, even with correct code"

        # OTP key should still be present (lockout check short-circuits before GETDEL)
        from app.otp.service import _otp_key
        assert r.exists(_otp_key(user_id, purpose)), \
            "OTP key must NOT be consumed when lockout blocks verify"



# New: resend cooldown

@pytest.mark.asyncio
async def test_resend_blocked_during_cooldown(r):
    """resend_otp() must raise ValueError when cooldown key is active."""
    user_id = 20
    purpose = "checkin:1"

    with patch("app.otp.service.get_redis", return_value=r):
        # First OTP sets cooldown
        await store_otp(user_id, purpose)

        # Immediate resend must be blocked
        with pytest.raises(ValueError, match="Resend cooldown active"):
            await resend_otp(user_id, purpose)


@pytest.mark.asyncio
async def test_resend_allowed_after_cooldown_expires(r):
    """resend_otp() must succeed once the cooldown key has expired."""
    user_id = 21
    purpose = "checkin:2"

    with patch("app.otp.service.get_redis", return_value=r):
        await store_otp(user_id, purpose)

        # Simulate cooldown expiry by deleting the key directly
        r.delete(_cooldown_key(user_id, purpose))

        # Resend should now succeed
        new_code = await resend_otp(user_id, purpose)
        assert len(new_code) == 6 and new_code.isdigit(), \
            f"Resend should return a valid 6-digit code, got: {new_code!r}"


@pytest.mark.asyncio
async def test_initial_store_does_not_enforce_cooldown(r):
    """store_otp() (initial request) must NOT check the cooldown key."""
    user_id = 22
    purpose = "create_switch"

    with patch("app.otp.service.get_redis", return_value=r):
        # Set cooldown manually (simulating a previous session)
        r.set(_cooldown_key(user_id, purpose), "1", ex=60)

        # store_otp (initial) should raise ValueError about existing OTP, NOT cooldown
        # But since there's no existing OTP key, it should succeed
        code = await store_otp(user_id, purpose)
        assert len(code) == 6 and code.isdigit()

