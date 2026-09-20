"""tests/test_deadline_warning.py -- Task 4: send_deadline_warning + check_and_warn_switches (sec 8, sec 14).

Tests:
  1. Idempotency -- second enqueueing within 24-h window is a no-op (Redis NX key).
  2. Inactive switch guard -- task returns early without sending when status != "active".
  3. Beat scanner window -- only switches with deadline in [now, now+24h] are selected.
  4. Guard released on SMTP failure -- retry can re-acquire the NX key.
  5. No warning sent when owner user not found in DB.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import fakeredis
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_switch(switch_id: int, status: str = "active", hours_until_deadline: float = 12.0) -> MagicMock:
    now = datetime.now(timezone.utc)
    sw = MagicMock()
    sw.id = switch_id
    sw.status = status
    sw.user_id = 100
    sw.next_deadline = now + timedelta(hours=hours_until_deadline)
    sw.recipient_email = "recipient@example.com"
    return sw


def _make_user(user_id: int = 100, email: str = "owner@example.com") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = email
    return u


# ---------------------------------------------------------------------------
# Test 1 -- Idempotency: second call within 24h is a no-op
# ---------------------------------------------------------------------------

class TestSendDeadlineWarningIdempotency:
    def test_second_call_is_noop(self):
        """Once the Redis NX key is set, a second task invocation must not re-send."""
        r = fakeredis.FakeRedis(decode_responses=True)
        switch_id = 42
        warning_key = f"warning:sent:{switch_id}"

        # Pre-set the key as if a previous run already sent the warning
        r.set(warning_key, "1", ex=86400)

        sent_emails = []

        def fake_smtp(to, subject, body_text, body_html=None):
            sent_emails.append(to)

        switch = _make_switch(switch_id)

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.scalar_one_or_none.return_value = switch
        mock_engine = MagicMock()

        with patch("app.core.redis_client.get_redis", return_value=r), \
             patch("app.tasks.email_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.email_tasks._send_smtp_email", side_effect=fake_smtp):
            from app.tasks.email_tasks import send_deadline_warning
            send_deadline_warning.apply(args=[switch_id])

        assert sent_emails == [], "No email should be sent when warning:sent key already exists"

    def test_first_call_sets_key_and_sends(self):
        """First call should set the Redis key and send the email."""
        r = fakeredis.FakeRedis(decode_responses=True)
        switch_id = 43
        warning_key = f"warning:sent:{switch_id}"

        assert r.get(warning_key) is None  # not set yet

        sent_emails = []

        def fake_smtp(to, subject, body_text, body_html=None):
            sent_emails.append(to)

        switch = _make_switch(switch_id)
        user = _make_user()

        mock_result_switch = MagicMock()
        mock_result_switch.scalar_one_or_none.return_value = switch
        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = user

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.side_effect = [mock_result_switch, mock_result_user]
        mock_engine = MagicMock()

        with patch("app.core.redis_client.get_redis", return_value=r), \
             patch("app.tasks.email_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.email_tasks._send_smtp_email", side_effect=fake_smtp):
            from app.tasks.email_tasks import send_deadline_warning
            send_deadline_warning.apply(args=[switch_id])

        assert sent_emails == ["owner@example.com"], "Warning email should be sent on first call"
        assert r.get(warning_key) == "1", "Redis key must be set after successful send"


# ---------------------------------------------------------------------------
# Test 2 -- Inactive switch guard
# ---------------------------------------------------------------------------

class TestInactiveSwitchGuard:
    @pytest.mark.parametrize("status", ["triggered", "cancelled", "triggering", "failed_reveal"])
    def test_non_active_switch_is_skipped(self, status):
        """Task should skip silently when the switch is no longer active."""
        r = fakeredis.FakeRedis(decode_responses=True)
        switch_id = 50

        sent_emails = []

        def fake_smtp(to, subject, body_text, body_html=None):
            sent_emails.append(to)

        switch = _make_switch(switch_id, status=status)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = switch

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value = mock_result
        mock_engine = MagicMock()

        with patch("app.core.redis_client.get_redis", return_value=r), \
             patch("app.tasks.email_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.email_tasks._send_smtp_email", side_effect=fake_smtp):
            from app.tasks.email_tasks import send_deadline_warning
            send_deadline_warning.apply(args=[switch_id])

        assert sent_emails == [], f"Should not send warning for status={status}"
        # Guard key must be released so future warnings are not silently eaten
        assert r.get(f"warning:sent:{switch_id}") is None, "Guard key must be deleted for non-active switch"


# ---------------------------------------------------------------------------
# Test 3 -- Beat scanner window (check_and_warn_switches)
# ---------------------------------------------------------------------------

class TestCheckAndWarnSwitchesScannerWindow:
    def test_only_switches_within_24h_window_are_enqueued(self):
        """
        check_and_warn_switches should enqueue exactly the switches whose deadline
        falls in [now, now+24h].
        """
        inside_window_ids = [10, 11]

        enqueued = []

        class FakeDelayable:
            def delay(self, switch_id):
                enqueued.append(switch_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = inside_window_ids

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value = mock_result
        mock_engine = MagicMock()

        fake_task = FakeDelayable()

        with patch("app.tasks.beat_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.beat_tasks.send_deadline_warning", fake_task, create=True):
            from app.tasks.beat_tasks import check_and_warn_switches
            # Patch the import inside the task body
            with patch("app.tasks.email_tasks.send_deadline_warning", fake_task):
                check_and_warn_switches.apply()

        assert sorted(enqueued) == sorted(inside_window_ids), (
            f"Expected {inside_window_ids} to be enqueued, got {enqueued}"
        )

    def test_no_candidates_does_not_enqueue(self):
        """When no switches are in the warning window, nothing is enqueued."""
        enqueued = []

        class FakeDelayable:
            def delay(self, switch_id):
                enqueued.append(switch_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value = mock_result
        mock_engine = MagicMock()

        with patch("app.tasks.beat_tasks._get_sync_session", return_value=(mock_session, mock_engine)):
            from app.tasks.beat_tasks import check_and_warn_switches
            check_and_warn_switches.apply()

        assert enqueued == [], "Nothing should be enqueued when no candidates"


# Test 4 -- Guard is released on SMTP failure so retry can re-acquire

class TestGuardReleasedOnSmtpFailure:
    def test_guard_key_deleted_when_smtp_fails(self):
        """On SMTP failure the guard key must be deleted so retry can re-acquire the NX key."""
        r = fakeredis.FakeRedis(decode_responses=True)
        switch_id = 60
        warning_key = f"warning:sent:{switch_id}"

        switch = _make_switch(switch_id)
        user = _make_user()

        # Use a rotating index so the mock never raises StopIteration on retry
        results = [
            MagicMock(**{"scalar_one_or_none.return_value": switch}),
            MagicMock(**{"scalar_one_or_none.return_value": user}),
        ]
        call_num = [0]

        def session_execute(*a, **kw):
            i = min(call_num[0], len(results) - 1)
            call_num[0] += 1
            return results[i]

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.side_effect = session_execute
        mock_engine = MagicMock()

        # Wrap r.delete to track if the guard key was deleted
        key_was_deleted = [False]
        orig_delete = r.delete

        def tracking_delete(*keys):
            if warning_key in keys:
                key_was_deleted[0] = True
            return orig_delete(*keys)

        r.delete = tracking_delete

        def exploding_smtp(to, subject, body_text, body_html=None):
            raise ConnectionRefusedError("SMTP down")

        with patch("app.core.redis_client.get_redis", return_value=r), \
             patch("app.tasks.email_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.email_tasks._send_smtp_email", side_effect=exploding_smtp):
            from app.tasks.email_tasks import send_deadline_warning
            send_deadline_warning.apply(args=[switch_id], throw=False)

        assert key_was_deleted[0], (
            "r.delete(warning_key) must be called on SMTP failure so retry can re-acquire NX key"
        )


# ---------------------------------------------------------------------------
# Test 5 -- Missing owner user
# ---------------------------------------------------------------------------

class TestMissingOwnerUser:
    def test_no_email_sent_when_user_not_found(self):
        """Task must not crash and must release guard when owner user is not found."""
        r = fakeredis.FakeRedis(decode_responses=True)
        switch_id = 70
        warning_key = f"warning:sent:{switch_id}"

        switch = _make_switch(switch_id)

        mock_result_switch = MagicMock()
        mock_result_switch.scalar_one_or_none.return_value = switch
        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = None  # user not found

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.side_effect = [mock_result_switch, mock_result_user]
        mock_engine = MagicMock()

        sent_emails = []

        def fake_smtp(to, subject, body_text, body_html=None):
            sent_emails.append(to)

        with patch("app.core.redis_client.get_redis", return_value=r), \
             patch("app.tasks.email_tasks._get_sync_session", return_value=(mock_session, mock_engine)), \
             patch("app.tasks.email_tasks._send_smtp_email", side_effect=fake_smtp):
            from app.tasks.email_tasks import send_deadline_warning
            send_deadline_warning.apply(args=[switch_id])

        assert sent_emails == [], "No email should be sent when owner user is not found"
        assert r.get(warning_key) is None, "Guard key must be cleaned up when user not found"
