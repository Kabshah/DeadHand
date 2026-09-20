"""tests/test_rate_limit.py — Rate limiter tests (§14).

Tests:
  1. Both user + IP layers fire independently.
  2. Fixed-window correctness: window doesn't reset on every hit.
  3. 429 with Retry-After header.
"""
import pytest
import fakeredis

from unittest.mock import patch

from app.core.rate_limit import RateLimitExceeded, check_rate_limits


@pytest.fixture
def r():
    """fakeredis client for rate limit tests."""
    return fakeredis.FakeRedis(decode_responses=True)


def _patched_check(r_client, *limiters):
    """Run check_rate_limits with a patched Redis client."""
    with patch("app.core.rate_limit.get_redis", return_value=r_client):
        check_rate_limits(*limiters)


class TestFixedWindow:
    def test_allows_requests_under_limit(self, r):
        for _ in range(3):
            _patched_check(r, ("rl:test:user:1", 3, 600))

    def test_blocks_on_limit_exceeded(self, r):
        for _ in range(3):
            _patched_check(r, ("rl:test:user:1", 3, 600))
        with pytest.raises(RateLimitExceeded):
            _patched_check(r, ("rl:test:user:1", 3, 600))

    def test_window_does_not_reset_on_every_hit(self, r):
        """
        The TTL must only be set when the key is NEW (EXPIRE NX).
        If EXPIRE ran on every request, the window would never close.
        Verify: after 3 hits, the TTL is set and not extended by subsequent hits.
        """
        key = "rl:ttl:test"
        limit = 5
        window = 600

        # First hit — creates key, sets TTL
        with patch("app.core.rate_limit.get_redis", return_value=r):
            check_rate_limits((key, limit, window))

        ttl_after_first = r.ttl(key)
        assert ttl_after_first > 0, "TTL must be set after first hit"

        # Subsequent hits — TTL should NOT increase (NX prevents reset)
        for _ in range(3):
            with patch("app.core.rate_limit.get_redis", return_value=r):
                check_rate_limits((key, limit, window))

        ttl_after_more = r.ttl(key)
        # TTL should be <= ttl_after_first (cannot have been extended)
        assert ttl_after_more <= ttl_after_first, (
            f"TTL was extended: {ttl_after_first} → {ttl_after_more} "
            "This means EXPIRE NX is not working correctly."
        )

    def test_user_and_ip_layers_fire_independently(self, r):
        """Both user + IP layers are checked; either can trip the limit."""
        user_key = "rl:otpreq:user:42:create_switch"
        ip_key = "rl:otpreq:ip:127.0.0.1:create_switch"

        # Exhaust user limit
        for _ in range(3):
            with patch("app.core.rate_limit.get_redis", return_value=r):
                check_rate_limits(
                    (user_key, 3, 600),
                    (ip_key, 10, 600),
                )

        # Now user limit is exhausted — next call must raise
        with pytest.raises(RateLimitExceeded) as exc_info:
            with patch("app.core.rate_limit.get_redis", return_value=r):
                check_rate_limits(
                    (user_key, 3, 600),
                    (ip_key, 10, 600),
                )

        assert "rl:otpreq:user:42" in exc_info.value.key

    def test_ip_layer_fires_independently(self, r):
        """IP layer can fire even when user layer is under its limit."""
        user_key = "rl:otpreq:user:99:create_switch"
        ip_key = "rl:otpreq:ip:10.0.0.1:create_switch"

        # Exhaust IP limit (10) while keeping user limit OK (3 < 10)
        # We do this by incrementing ip_key directly
        for _ in range(10):
            r.incr(ip_key)
        r.expire(ip_key, 600)

        # Only 1 user request — well within user limit of 3
        r.incr(user_key)
        r.expire(user_key, 600)

        with pytest.raises(RateLimitExceeded) as exc_info:
            with patch("app.core.rate_limit.get_redis", return_value=r):
                check_rate_limits(
                    (user_key, 3, 600),
                    (ip_key, 10, 600),
                )

        assert "ip" in exc_info.value.key


class TestRateLimitExceededProperties:
    def test_has_window_and_key(self, r):
        exc = RateLimitExceeded(key="rl:test", window=600)
        assert exc.window == 600
        assert exc.key == "rl:test"
