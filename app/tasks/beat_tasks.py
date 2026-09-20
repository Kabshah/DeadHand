"""app/tasks/beat_tasks.py — Task 2: check_and_trigger_switches; Task 4 scanner: check_and_warn_switches (§8).

Task 2 (Beat, every 5 min):
  1. Reads overdue switch IDs from the Redis sorted set.
  2. For each candidate:
     a. Acquires per-switch Redis lock (SET NX EX 30).
     b. Atomically transitions status: active → triggering (WHERE status='active').
     c. Enqueues Task 3 (switch_id only — plaintext NEVER passed over broker).
     d. Releases lock with Lua compare-and-del.

Task 4 scanner (Beat, every 5 min):
  - Queries DB for active switches with next_deadline within the next 24 hours.
  - For each, enqueues send_deadline_warning (which deduplicates via Redis NX key).
  - Uses DB query, not the sorted set, because the sorted set only tracks *overdue*
    deadlines (score <= now), not upcoming ones.

Task 2 owns ONLY the active → triggering transition.
Task 3 owns the triggering → triggered transition.

Concurrency guards (§10.3):
  - Layer 1: Redis lock — first worker proceeds; second skips.
  - Layer 2: WHERE status='active' — even without the lock, only one UPDATE lands.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.locks import acquire_lock, release_lock
from app.core.redis_client import get_redis
from app.switches.models import Switch
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_DEADLINE_ZSET = "switches:deadlines"


def _get_sync_session():
    from sqlalchemy import create_engine

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "", 1).replace("+aiosqlite", "", 1)
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine), engine


@celery_app.task(
    name="app.tasks.beat_tasks.check_and_trigger_switches",
    bind=True,
    acks_late=True,
    max_retries=0,  # Beat task should not retry — it runs again in 5 min
)
def check_and_trigger_switches(self) -> None:
    """Scan for overdue switches and transition them to 'triggering' (Task 2, §8)."""
    now_ts = datetime.now(timezone.utc).timestamp()
    r = get_redis()

    # Step 1: Get all candidate switch IDs whose deadline has passed
    candidates: list[str] = r.zrangebyscore(_DEADLINE_ZSET, "-inf", now_ts)

    if not candidates:
        logger.debug("Beat: no overdue switches found")
        return

    logger.info("Beat: found %d overdue switch candidate(s): %s", len(candidates), candidates)

    for switch_id_str in candidates:
        switch_id = int(switch_id_str)
        _process_candidate(switch_id)


def _process_candidate(switch_id: int) -> None:
    """Process a single overdue switch candidate."""
    logger.info("Beat: processing switch_id=%d", switch_id)

    # Step 2a: Acquire per-switch Redis lock
    token = acquire_lock(switch_id)
    if token is None:
        logger.info("Beat: switch_id=%d lock not acquired — skipping (another worker has it)", switch_id)
        return

    logger.info("Beat: switch_id=%d lock acquired", switch_id)

    session, engine = _get_sync_session()
    try:
        with session:
            # Step 2b: Atomic DB transition: active → triggering
            now = datetime.now(timezone.utc)
            result = session.execute(
                update(Switch)
                .where(Switch.id == switch_id, Switch.status == "active")
                .values(
                    status="triggering",
                    version=Switch.version + 1,
                    updated_at=now,
                )
            )
            rows_affected: int = result.rowcount

            if rows_affected == 0:
                # Someone else already moved the row — skip
                logger.info(
                    "Beat: switch_id=%d 0 rows affected — already moved by another process, skipping",
                    switch_id,
                )
                session.rollback()
                return

            session.commit()
            logger.info("Beat: switch_id=%d ✓ DB status → triggering", switch_id)

        # Step 2c: Enqueue Task 3 (switch_id only — plaintext NEVER over broker, §11)
        from app.tasks.email_tasks import send_reveal_email
        send_reveal_email.delay(switch_id)
        logger.info(
            "Beat: switch_id=%d ✓ send_reveal_email enqueued — SWITCH TRIGGERED 🔥",
            switch_id,
        )

    except Exception:
        logger.exception("Beat: error processing switch_id=%d", switch_id)
    finally:
        # Step 2d: Release lock with compare-and-del
        released = release_lock(switch_id, token)
        logger.info("Beat: switch_id=%d lock released=%s", switch_id, released)
        engine.dispose()


# Task 4 scanner — check_and_warn_switches

_WARNING_WINDOW_HOURS = 24  # warn when deadline is within this many hours


@celery_app.task(
    name="app.tasks.beat_tasks.check_and_warn_switches",
    bind=True,
    acks_late=True,
    max_retries=0,  # Beat task should not retry — it runs again in 5 min
)
def check_and_warn_switches(self) -> None:  # noqa: ANN001
    """Scan for switches approaching their deadline and enqueue Task 4 warnings (§8).

    Queries the DB (not the sorted set — the sorted set only tracks overdue deadlines)
    for active switches whose next_deadline falls between now and now + 24 h.

    send_deadline_warning handles its own idempotency via a Redis NX key, so
    enqueuing the same switch_id multiple times within a Beat cycle is safe.
    """
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=_WARNING_WINDOW_HOURS)

    session, engine = _get_sync_session()
    try:
        with session:
            rows = session.execute(
                select(Switch.id)
                .where(
                    Switch.status == "active",
                    Switch.next_deadline >= now,
                    Switch.next_deadline <= window_end,
                )
            ).scalars().all()

        if not rows:
            logger.debug("Beat/warn: no switches approaching deadline in next %dh", _WARNING_WINDOW_HOURS)
            return

        logger.info(
            "Beat/warn: found %d switch(es) with deadline in next %dh — enqueuing warnings",
            len(rows), _WARNING_WINDOW_HOURS,
        )

        from app.tasks.email_tasks import send_deadline_warning

        for switch_id in rows:
            send_deadline_warning.delay(switch_id)
            logger.debug("Beat/warn: enqueued send_deadline_warning for switch_id=%d", switch_id)

    except Exception:
        logger.exception("Beat/warn: error in check_and_warn_switches")
    finally:
        engine.dispose()
