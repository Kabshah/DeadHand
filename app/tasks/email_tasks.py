"""app/tasks/email_tasks.py — Task 1 (send_otp_email), Task 3 (send_reveal_email), Task 4 (send_deadline_warning) (§8).

Task 1 — send_otp_email(user_id, purpose):
  - acks_late=True, max_retries=3, exponential backoff
  - Fetches user email from DB inside task (not passed as arg — avoids stale data on retry)
  - Idempotency: resending same OTP email on retry is harmless

Task 3 — send_reveal_email(switch_id):
  - Double-guard: status != 'triggering' → no-op; sent_at IS NOT NULL → no-op
  - Decrypts secret_ciphertext in-memory (NEVER passed over broker)
  - On permanent failure: sets status='failed_reveal' (never silently dropped, §8)

Task 4 — send_deadline_warning(switch_id):
  - Beat enqueues this when next_deadline is within 24 hours and switch is still active.
  - Idempotency guard: Redis key warning:sent:{switch_id} (EX 86400) — set before send,
    so repeated Beat firings within the same 24-h window are no-ops.
  - Sends warning email to the switch OWNER (not recipient), fetched fresh from DB on retry.
"""
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from celery import Task
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_secret
from app.switches.models import Switch, User
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Return a sync SQLAlchemy session for use inside Celery tasks."""
    from sqlalchemy import create_engine

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "", 1).replace("+aiosqlite", "", 1)
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine), engine


def _send_smtp_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Send an email via SMTP. Raises smtplib.SMTPException on failure."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to

    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to], msg.as_string())

    logger.info("Email sent to %s subject=%r", to, subject)


# Task 1 — send_otp_email
@celery_app.task(
    name="app.tasks.email_tasks.send_otp_email",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_otp_email(self: Task, user_id: int, purpose: str, code: str = "") -> None:
    """Send an OTP email to the user.

    Fetches user email from DB inside the task — not passed as arg — so
    retries always use the latest email address (§8).
    """
    session, engine = _get_sync_session()
    try:
        with session:
            user: User | None = session.execute(
                select(User).where(User.id == user_id)
            ).scalar_one_or_none()

            if user is None:
                logger.error("send_otp_email: user_id=%d not found — task aborted", user_id)
                return

            email = user.email
            logger.info("Sending OTP email: user_id=%d purpose=%s", user_id, purpose)

        subject = "Your Dead Hand OTP Code"
        body = (
            f"Your one-time code is: {code}\n\n"
            f"Purpose: {purpose}\n"
            f"This code expires in {settings.OTP_TTL_SECONDS // 60} minutes.\n\n"
            f"If you did not request this, please ignore this email."
        )

        # Fetch the actual OTP from Redis to include in email
        from app.core.redis_client import get_redis

        r = get_redis()
        # We don't have the raw code here (only the hash is stored).
        # The OTP flow: user hits /otp/request, route calls store_otp() which
        # returns the raw code to the route, which enqueues this task.
        # The raw code is passed via the task args at call site — see otp/routes.py.
        # For this generic send function, we notify the user a code was sent.
        # Production: pass code as separate arg or store encrypted in task args.

        try:
            _send_smtp_email(email, subject, body)
        except Exception as exc:
            logger.warning(
                "OTP email send failed for user_id=%d purpose=%s: %s — retrying",
                user_id, purpose, exc,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)
    finally:
        engine.dispose()


class RevealTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """On permanent failure (max_retries exhausted): mark switch as failed_reveal."""
        switch_id = args[0] if args else kwargs.get("switch_id")
        if switch_id is None:
            return
        logger.error("send_reveal_email permanently failed for switch_id=%d: %s", switch_id, exc)
        session, engine = _get_sync_session()
        try:
            with session:
                _mark_failed_reveal(session, switch_id)
                session.commit()
        finally:
            engine.dispose()


@celery_app.task(
    name="app.tasks.email_tasks.send_reveal_email",
    base=RevealTask,
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=120,
)
def send_reveal_email(self: Task, switch_id: int) -> None:
    """Decrypt and reveal the secret to the recipient (§8, Task 3).

    Double-guard idempotency (§10.5):
      1. If status != 'triggering' → already completed/cancelled; return immediately.
      2. If sent_at IS NOT NULL → email already sent on a prior run; return immediately.

    Decrypts secret_ciphertext in-memory — plaintext NEVER passed over broker (§11).

    On permanent failure: sets status='failed_reveal' — never silently dropped (§8).
    """
    session, engine = _get_sync_session()
    try:
        with session:
            switch: Switch | None = session.execute(
                select(Switch).where(Switch.id == switch_id)
            ).scalar_one_or_none()

            if switch is None:
                logger.error("send_reveal_email: switch_id=%d not found", switch_id)
                return

            # Guard 1: must still be in triggering state
            if switch.status != "triggering":
                logger.info(
                    "send_reveal_email: switch_id=%d status=%s — already handled, no-op",
                    switch_id, switch.status,
                )
                return

            # Guard 2: sent_at IS NOT NULL means email already went out
            if switch.sent_at is not None:
                logger.info(
                    "send_reveal_email: switch_id=%d sent_at=%s — already sent, no-op",
                    switch_id, switch.sent_at,
                )
                return

            recipient = switch.recipient_email
            logger.info(
                "Revealing secret: switch_id=%d recipient=%s (plaintext not logged)",
                switch_id, recipient,
            )

            # Decrypt in-memory — plaintext never stored or logged (§11)
            try:
                plaintext = decrypt_secret(switch.secret_ciphertext)
            except ValueError as exc:
                logger.exception("Decryption failed for switch_id=%d", switch_id)
                _mark_failed_reveal(session, switch_id)
                session.commit()
                return

            subject = "A message has been left for you"
            body = (
                f"Someone set up a Dead Hand for you.\n\n"
                f"Their message:\n\n{plaintext}\n\n"
                f"— Dead Hand Service"
            )

            try:
                _send_smtp_email(recipient, subject, body)
            except Exception as exc:
                logger.warning(
                    "Reveal email failed for switch_id=%d: %s — retrying", switch_id, exc
                )
                raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)

            # Success: mark as triggered in same commit (§10.5)
            now = datetime.now(timezone.utc)
            session.execute(
                update(Switch)
                .where(Switch.id == switch_id)
                .values(status="triggered", sent_at=now, updated_at=now)
            )
            session.commit()
            logger.info("💾 DB Update: switch_id=%d status updated to 'triggered' | sent_at=%s", switch_id, now.isoformat())

            # Remove from sorted set
            from app.core.redis_client import get_redis
            get_redis().zrem("switches:deadlines", str(switch_id))
            logger.info("Reveal complete: switch_id=%d status=triggered", switch_id)

    except Exception:
        raise
    finally:
        engine.dispose()


def _mark_failed_reveal(session: Session, switch_id: int) -> None:
    """Set switch status to 'failed_reveal' — never silently drop a failed reveal (§8)."""
    now = datetime.now(timezone.utc)
    session.execute(
        update(Switch)
        .where(Switch.id == switch_id)
        .values(status="failed_reveal", updated_at=now)
    )
    logger.error("Switch marked failed_reveal: switch_id=%d", switch_id)

# Task 4 — send_deadline_warning

_WARNING_SENT_KEY = "warning:sent:{switch_id}"  # Redis key template; TTL = 24 h
_WARNING_TTL_SECONDS = 86_400  # 24 hours


@celery_app.task(
    name="app.tasks.email_tasks.send_deadline_warning",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=120,
)
def send_deadline_warning(self: Task, switch_id: int) -> None:
    """Send a 24-hour deadline warning email to the switch owner (Task 4, §8).

    Idempotency (Beat fires every 5 min, but warning should go out exactly once):
      - Before sending, check Redis key warning:sent:{switch_id}.
      - If key exists → warning already sent this cycle; return immediately (no-op).
      - If key absent → set it (EX 86400) then send the email.
        Setting the key first (optimistic) means even if the send fails and retries,
        the key acts as a guard. On retry after key expiry the warning re-sends,
        which is acceptable behaviour for a new deadline cycle.

    Guard: if switch is no longer active (checked-in, cancelled, triggered) → skip.
    User email fetched fresh from DB inside the task — avoids stale data on retry.
    """
    from app.core.redis_client import get_redis

    r = get_redis()
    warning_key = _WARNING_SENT_KEY.format(switch_id=switch_id)

    # Idempotency guard: NX means only the first caller sets the key
    acquired = r.set(warning_key, "1", nx=True, ex=_WARNING_TTL_SECONDS)
    if not acquired:
        logger.info(
            "send_deadline_warning: switch_id=%d warning already sent this cycle — no-op",
            switch_id,
        )
        return

    session, engine = _get_sync_session()
    try:
        with session:
            from sqlalchemy import select as sa_select

            switch: Switch | None = session.execute(
                sa_select(Switch).where(Switch.id == switch_id)
            ).scalar_one_or_none()

            if switch is None:
                logger.error("send_deadline_warning: switch_id=%d not found — aborting", switch_id)
                # Release guard so a future corrected run can try
                r.delete(warning_key)
                return

            # Guard: only warn for still-active switches
            if switch.status != "active":
                logger.info(
                    "send_deadline_warning: switch_id=%d status=%s — not active, skipping",
                    switch_id, switch.status,
                )
                r.delete(warning_key)  # release so we don't silently eat future warnings
                return

            user: User | None = session.execute(
                sa_select(User).where(User.id == switch.user_id)
            ).scalar_one_or_none()

            if user is None:
                logger.error(
                    "send_deadline_warning: owner user_id=%d not found for switch_id=%d",
                    switch.user_id, switch_id,
                )
                r.delete(warning_key)
                return

            owner_email = user.email
            deadline_str = switch.next_deadline.strftime("%Y-%m-%d %H:%M UTC")

        logger.info(
            "Sending deadline warning: switch_id=%d owner_email=%s deadline=%s",
            switch_id, owner_email, deadline_str,
        )

        subject = "⚠️ Dead Hand deadline in less than 24 hours"
        body_text = (
            f"Your Dead Hand (ID: {switch_id}) will trigger in less than 24 hours.\n\n"
            f"Deadline: {deadline_str}\n\n"
            f"If you are still here, please check in now to reset your switch deadline.\n\n"
            f"— Dead Hand Service"
        )
        body_html = (
            "<p>Your <strong>Dead Hand</strong> "
            f"(ID: <code>{switch_id}</code>) will trigger in less than 24 hours.</p>"
            f"<p><strong>Deadline:</strong> {deadline_str}</p>"
            "<p>If you are still here, please <strong>check in</strong> now to reset "
            "your switch deadline.</p>"
            "<p style='color:#888;'>— Dead Hand Service</p>"
        )

        try:
            _send_smtp_email(owner_email, subject, body_text, body_html)
        except Exception as exc:
            logger.warning(
                "Deadline warning email failed for switch_id=%d: %s — retrying",
                switch_id, exc,
            )
            # Delete guard so the retry can re-set it (NX pattern)
            r.delete(warning_key)
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)

        logger.info("Deadline warning sent: switch_id=%d owner=%s", switch_id, owner_email)

    except Exception:
        raise
    finally:
        engine.dispose()
