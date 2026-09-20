"""app/switches/service.py — Single source of truth for all status transitions + Redis sync (§9, §15).

This module is called from BOTH route handlers and Celery tasks.
All Redis sync logic lives here — never duplicated elsewhere.

Redis key table managed here (§9):
  - switches:deadlines  sorted set  score = deadline Unix timestamp
    CREATE  → ZADD
    CHECKIN → ZADD (updates score for existing member automatically)
    CANCEL  → ZREM
    TRIGGER → ZREM (done by Task 3 after email confirmed)
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.redis_client import get_redis
from app.switches.models import Switch

logger = logging.getLogger(__name__)

_DEADLINE_ZSET = "switches:deadlines"


# Helpers

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _compute_deadline(interval_hours: float) -> datetime:
    return _now_utc() + timedelta(hours=interval_hours)


def _zadd_deadline(switch_id: int, deadline: datetime) -> None:
    """Add or update the deadline score in the sorted set."""
    r = get_redis()
    r.zadd(_DEADLINE_ZSET, {str(switch_id): deadline.timestamp()})
    logger.debug("ZADD switches:deadlines switch_id=%d deadline=%s", switch_id, deadline.isoformat())


def _zrem_deadline(switch_id: int) -> None:
    """Remove a switch from the deadline sorted set."""
    r = get_redis()
    r.zrem(_DEADLINE_ZSET, str(switch_id))
    logger.debug("ZREM switches:deadlines switch_id=%d", switch_id)


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

async def create_switch(
    db: AsyncSession,
    user_id: int,
    recipient_email: str,
    interval_hours: float,
    secret_message: str,
) -> Switch:
    """Create a new active switch.

    Steps:
      1. Check user hasn't exceeded MAX_SWITCHES_PER_USER.
      2. Encrypt secret in-memory (plaintext never stored or logged).
      3. INSERT switch.
      4. ZADD to Redis sorted set.
    """
    # Cap active switches per user (§11)
    result = await db.execute(
        select(Switch).where(
            Switch.user_id == user_id,
            Switch.status.in_(["active", "triggering"]),
        )
    )
    active_switches = result.scalars().all()
    if len(active_switches) >= settings.MAX_SWITCHES_PER_USER:
        raise ValueError(
            f"Maximum of {settings.MAX_SWITCHES_PER_USER} active switches per user reached"
        )

    now = _now_utc()
    deadline = _compute_deadline(interval_hours)
    ciphertext = encrypt_secret(secret_message)  # plaintext not logged (§11)

    switch = Switch(
        user_id=user_id,
        secret_ciphertext=ciphertext,
        recipient_email=recipient_email,
        interval_hours=interval_hours,
        next_deadline=deadline,
        status="active",
        version=0,
        sent_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(switch)
    await db.flush()  # get the assigned ID

    # Redis sync — DB committed, now update cache
    _zadd_deadline(switch.id, deadline)
    logger.info("Switch created: switch_id=%d user_id=%d deadline=%s", switch.id, user_id, deadline.isoformat())
    return switch


async def checkin_switch(db: AsyncSession, switch_id: int, user_id: int) -> Switch:
    """Process a check-in: extend the deadline.

    Atomic UPDATE with WHERE status='active' guards the checkin-vs-trigger race (§10.1).
    Returns 410 if switch is not active (triggering/triggered/cancelled).
    Returns 404 if switch not found or not owned by user.
    """
    now = _now_utc()

    # First verify ownership and fetch current state
    result = await db.execute(
        select(Switch).where(Switch.id == switch_id, Switch.user_id == user_id)
    )
    switch: Switch | None = result.scalar_one_or_none()
    if switch is None:
        raise LookupError(f"Switch {switch_id} not found")

    if switch.status != "active":
        raise ValueError(f"Switch {switch_id} is {switch.status} — cannot check in")

    new_deadline = _compute_deadline(switch.interval_hours)

    # Atomic update: only succeeds if status is still 'active'
    stmt = (
        update(Switch)
        .where(Switch.id == switch_id, Switch.user_id == user_id, Switch.status == "active")
        .values(
            next_deadline=new_deadline,
            version=Switch.version + 1,
            updated_at=now,
        )
        .returning(Switch)
    )
    result2 = await db.execute(stmt)
    updated: Switch | None = result2.scalar_one_or_none()

    if updated is None:
        # Race: another process moved the status between our SELECT and UPDATE
        raise ValueError(f"Switch {switch_id} is no longer active (race condition)")

    # Redis sync — ZADD updates score for existing member (no ZREM needed, §9)
    _zadd_deadline(switch_id, new_deadline)
    logger.info(
        "Check-in: switch_id=%d user_id=%d new_deadline=%s",
        switch_id, user_id, new_deadline.isoformat(),
    )
    return updated


async def cancel_switch(db: AsyncSession, switch_id: int, user_id: int) -> Switch:
    """Cancel a switch (must be active).

    Returns 404 if not found/not owned, 410 if already triggered/cancelled.
    """
    now = _now_utc()

    result = await db.execute(
        select(Switch).where(Switch.id == switch_id, Switch.user_id == user_id)
    )
    switch: Switch | None = result.scalar_one_or_none()
    if switch is None:
        raise LookupError(f"Switch {switch_id} not found")

    if switch.status not in ("active", "triggering"):
        raise ValueError(f"Switch {switch_id} is {switch.status} — cannot cancel")

    stmt = (
        update(Switch)
        .where(
            Switch.id == switch_id,
            Switch.user_id == user_id,
            Switch.status.in_(["active", "triggering"]),
        )
        .values(status="cancelled", version=Switch.version + 1, updated_at=now)
        .returning(Switch)
    )
    result2 = await db.execute(stmt)
    updated: Switch | None = result2.scalar_one_or_none()
    if updated is None:
        raise ValueError(f"Switch {switch_id} could not be cancelled (race condition)")

    _zrem_deadline(switch_id)
    logger.info("Switch cancelled: switch_id=%d user_id=%d", switch_id, user_id)
    return updated


async def get_switch(db: AsyncSession, switch_id: int, user_id: int) -> Switch:
    """Fetch a single switch owned by user. Raises LookupError if not found."""
    result = await db.execute(
        select(Switch).where(Switch.id == switch_id, Switch.user_id == user_id)
    )
    switch: Switch | None = result.scalar_one_or_none()
    if switch is None:
        raise LookupError(f"Switch {switch_id} not found")
    return switch


async def get_user_switches(db: AsyncSession, user_id: int, search: str | None = None) -> list[Switch]:
    """List all switches for a user, optionally filtered by search query."""
    stmt = select(Switch).where(Switch.user_id == user_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Switch.recipient_email.ilike(term),
                cast(Switch.id, String).ilike(term),
                Switch.status.ilike(term),
            )
        )
    stmt = stmt.order_by(Switch.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Startup rebuild (§9)
# ---------------------------------------------------------------------------

def rebuild_deadline_sorted_set(db_session_sync=None) -> None:
    """Rebuild switches:deadlines sorted set from DB (DB is source of truth).

    Called by the Celery worker_ready signal on every startup.
    Memurai doesn't persist data across restarts by default — if the sorted set
    is lost, Beat finds no candidates and switches silently never trigger.

    This function uses a sync DB session (Celery tasks are sync).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    # Convert asyncpg URL to sync for use in Celery context
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "", 1)
    engine = create_engine(sync_url, pool_pre_ping=True)

    with Session(engine) as session:
        rows = session.execute(
            select(Switch.id, Switch.next_deadline).where(Switch.status == "active")
        ).all()

    r = get_redis()
    r.delete(_DEADLINE_ZSET)
    if rows:
        r.zadd(_DEADLINE_ZSET, {str(row.id): row.next_deadline.timestamp() for row in rows})

    logger.info("Rebuilt switches:deadlines with %d active switches", len(rows))
    engine.dispose()
