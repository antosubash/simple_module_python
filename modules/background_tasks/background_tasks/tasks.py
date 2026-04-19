"""Internal Celery tasks registered by the background_tasks module itself.

- ``sweep_stuck_tasks`` flips ``running`` rows whose heartbeat has gone stale
  to ``stuck`` so the UI surfaces them and they become eligible for retry.
- ``purge_old_executions`` deletes terminal rows older than the configured
  retention so the history table stays bounded.

Both are driven by Celery beat; see :mod:`.celery_app`.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import delete, update

from background_tasks.constants import (
    DEFAULT_RETENTION_DAYS,
    DEFAULT_STUCK_AFTER_SECONDS,
    INTERNAL_TASK_PURGE_OLD,
    INTERNAL_TASK_SWEEP_STUCK,
    TERMINAL_STATUSES,
    TaskStatus,
)
from background_tasks.models import TaskExecution
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)


def _load_settings() -> BackgroundTasksSettings:
    """Build settings inside the worker process.

    The web-process ``register_settings`` attached them to ``app.state``,
    but the worker never sees that ``app.state``. Re-parsing from env here
    is the same deterministic source of truth.
    """
    return BackgroundTasksSettings()


@shared_task(name=INTERNAL_TASK_SWEEP_STUCK)
def sweep_stuck_tasks() -> int:
    """Flip ``running`` rows with stale heartbeats to ``stuck``.

    Returns the number of rows flipped — handy for metrics/log scraping.
    """
    # Avoid import-time coupling to settings (beat schedules this task
    # before the worker has hydrated settings in some edge cases).
    stuck_after = int(
        os.environ.get("SM_BG_TASKS_STUCK_AFTER_SECONDS", DEFAULT_STUCK_AFTER_SECONDS)
    )
    cutoff = datetime.now(UTC) - timedelta(seconds=stuck_after)

    with sync_session() as session:
        stmt = (
            update(TaskExecution)
            .where(
                TaskExecution.status == TaskStatus.RUNNING,
                TaskExecution.heartbeat_at < cutoff,
            )
            .values(status=TaskStatus.STUCK, finished_at=datetime.now(UTC))
        )
        result = session.execute(stmt)
        count = result.rowcount or 0
        if count:
            logger.warning("sweep_stuck_tasks flipped %d row(s) to stuck", count)
        return count


@shared_task(name=INTERNAL_TASK_PURGE_OLD)
def purge_old_executions() -> int:
    """Delete terminal rows older than the retention window."""
    retention_days = int(os.environ.get("SM_BG_TASKS_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    with sync_session() as session:
        result = session.execute(
            delete(TaskExecution)
            .where(TaskExecution.status.in_(list(TERMINAL_STATUSES)))
            .where(TaskExecution.finished_at < cutoff)
        )
        count = result.rowcount or 0
        if count:
            logger.info(
                "purge_old_executions removed %d row(s) older than %d days",
                count,
                retention_days,
            )
        return count
