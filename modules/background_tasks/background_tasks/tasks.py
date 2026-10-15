"""Internal Celery tasks registered by the background_tasks module itself.

- ``sweep_stuck_tasks`` flips ``running`` rows whose heartbeat has gone stale
  to ``stuck`` so the UI surfaces them and they become eligible for retry.
- ``purge_old_executions`` deletes terminal rows older than the configured
  retention so the history table stays bounded, and delivered outbox rows
  older than the same retention.
- ``dispatch_outbox`` / ``sweep_outbox`` deliver durable events (GH #459); see
  :mod:`.outbox_dispatch`.

Both are driven by Celery beat; see :mod:`.celery_app`.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Task, shared_task
from sqlalchemy import ColumnElement, and_, delete, or_, update

from background_tasks.constants import (
    DEFAULT_RETENTION_DAYS,
    DEFAULT_STUCK_AFTER_SECONDS,
    DEMO_ECHO_TASK,
    INTERNAL_TASK_DISPATCH_OUTBOX,
    INTERNAL_TASK_PURGE_OLD,
    INTERNAL_TASK_SWEEP_OUTBOX,
    INTERNAL_TASK_SWEEP_STUCK,
    TASK_STUCK_AFTER_ATTR,
    TERMINAL_STATUSES,
    OutboxStatus,
    TaskStatus,
)
from background_tasks.models import OutboxMessage, TaskExecution
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


@shared_task(name=DEMO_ECHO_TASK)
def demo_echo(message: str = "hello") -> dict[str, str]:
    """Trivial task used for end-to-end smoke tests of the Celery pipeline.

    Returns the input wrapped with a worker timestamp so a successful
    execution produces a non-empty ``result`` column in the admin UI.
    """
    logger.info("demo_echo received message=%r", message)
    return {"message": message, "at": datetime.now(UTC).isoformat()}


def stuck_thresholds(registry: Mapping[str, Any]) -> dict[str, int]:
    """Per-task stuck thresholds declared on the tasks in *registry*.

    A task opts in with ``@shared_task(name=..., stuck_after=seconds)``; Celery
    copies the option onto the task class. Read from the registry of the
    process running the sweep, which autodiscovers every module's tasks, so
    the threshold lives next to the task and needs no column or migration.
    """
    found: dict[str, int] = {}
    for name, task in registry.items():
        value = getattr(task, TASK_STUCK_AFTER_ATTR, None)
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            found[name] = max(1, int(value))
    return found


def _stale(now: datetime, stuck_after: int, overrides: dict[str, int]) -> ColumnElement[bool]:
    """Rows whose heartbeat is older than their own task's threshold."""
    clauses = [
        and_(
            TaskExecution.task_name.in_(names),
            TaskExecution.heartbeat_at < now - timedelta(seconds=seconds),
        )
        for seconds, names in _group_by_threshold(overrides).items()
    ]
    default = TaskExecution.heartbeat_at < now - timedelta(seconds=stuck_after)
    if overrides:
        default = and_(TaskExecution.task_name.not_in(list(overrides)), default)
    return or_(default, *clauses)


def _group_by_threshold(overrides: dict[str, int]) -> dict[int, list[str]]:
    groups: defaultdict[int, list[str]] = defaultdict(list)
    for name, seconds in overrides.items():
        groups[seconds].append(name)
    return groups


@shared_task(name=INTERNAL_TASK_SWEEP_STUCK, bind=True)
def sweep_stuck_tasks(self: Task) -> int:
    """Flip ``running`` rows with stale heartbeats to ``stuck``.

    "Stale" is per task: a task's own ``stuck_after`` (see
    :func:`stuck_thresholds`) wins over the global setting. Long jobs should
    also call :func:`background_tasks.heartbeat` as they go.

    Returns the number of rows flipped — handy for metrics/log scraping.
    """
    # Avoid import-time coupling to settings (beat schedules this task
    # before the worker has hydrated settings in some edge cases).
    stuck_after = int(
        os.environ.get("SM_BG_TASKS_STUCK_AFTER_SECONDS", DEFAULT_STUCK_AFTER_SECONDS)
    )
    now = datetime.now(UTC)
    overrides = stuck_thresholds(self.app.tasks)

    with sync_session() as session:
        stmt = (
            update(TaskExecution)
            .where(
                TaskExecution.status == TaskStatus.RUNNING,
                _stale(now, stuck_after, overrides),
            )
            .values(status=TaskStatus.STUCK, finished_at=now)
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
        delivered = session.execute(
            delete(OutboxMessage)
            .where(OutboxMessage.status == OutboxStatus.DELIVERED)
            .where(OutboxMessage.delivered_at < cutoff)
        )
        count += delivered.rowcount or 0
        if count:
            logger.info(
                "purge_old_executions removed %d row(s) older than %d days",
                count,
                retention_days,
            )
        return count


@shared_task(name=INTERNAL_TASK_DISPATCH_OUTBOX)
def dispatch_outbox(ids: list[str]) -> dict[str, int]:
    """Deliver the outbox rows a just-committed transaction wrote."""
    # Imported here: the dispatcher pulls in the async engine stack, which a
    # worker only needs once it actually delivers an event.
    from background_tasks.outbox_worker import run_dispatch

    return run_dispatch(list(ids))


@shared_task(name=INTERNAL_TASK_SWEEP_OUTBOX)
def sweep_outbox() -> dict[str, int]:
    """Deliver every due outbox row and reclaim expired leases (beat, every 30 s)."""
    from background_tasks.outbox_worker import run_dispatch

    return run_dispatch(None)
