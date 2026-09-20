"""app/tasks/celery_app.py — Celery app, Beat schedule, worker startup rebuild (§8, §9).

Windows note (§2a): Run with --pool=solo:
  celery -A app.tasks.celery_app worker --pool=solo --loglevel=info
  celery -A app.tasks.celery_app beat --loglevel=info
"""
import logging

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    "dead_switch",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.beat_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # acks_late: keep message in queue until task acknowledges (§10.5)
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Beat schedule — Task 2 and Task 4 scanner every 30 seconds (§8)
    beat_schedule={
        "check-and-trigger-switches": {
            "task": "app.tasks.beat_tasks.check_and_trigger_switches",
            "schedule": 30.0,  # every 30 seconds for responsive check-ins & warnings
        },
        "check-and-warn-switches": {
            "task": "app.tasks.beat_tasks.check_and_warn_switches",
            "schedule": 30.0,  # every 30 seconds
        },
    },
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs) -> None:
    """Rebuild switches:deadlines sorted set from DB on every worker startup (§9).

    Memurai doesn't persist data across restarts by default.
    If the sorted set is lost, Beat finds no candidates and switches silently
    never trigger — the worst possible silent failure mode.
    """
    setup_logging()
    logger.info("Worker ready — rebuilding deadline sorted set from DB...")
    try:
        from app.switches.service import rebuild_deadline_sorted_set
        from app.core.redis_client import load_lua_scripts

        load_lua_scripts()
        rebuild_deadline_sorted_set()
        logger.info("Deadline sorted set rebuild complete")
    except Exception:
        logger.exception("Failed to rebuild deadline sorted set on startup")
