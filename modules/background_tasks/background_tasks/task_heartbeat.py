"""Liveness for long-running task bodies (GH #451).

The signal handlers stamp ``heartbeat_at`` when a task starts and when it
finishes — nothing in between. :func:`~background_tasks.tasks.sweep_stuck_tasks`
treats a ``running`` row whose heartbeat is older than the stuck threshold as
a worker that died, and makes it retry-eligible. Without a way to check in
from *inside* the task, every job longer than the threshold was flagged stuck
and could be run a second time while the first was still working.

A task body calls :func:`heartbeat` from its loop. Writes are throttled per
task, in-process, so calling it on every iteration is cheap; and it is a
no-op outside a running task, so shared helpers can call it unconditionally.
"""

from __future__ import annotations

import logging
import threading
import time

from celery import current_task
from sqlalchemy import update

from background_tasks._signal_support import now_utc
from background_tasks.constants import HEARTBEAT_MIN_INTERVAL_SECONDS, TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)

_last_beat: dict[str, float] = {}
_lock = threading.Lock()


def _current_task_id() -> str | None:
    """The id of the Celery task executing on this thread, if any.

    ``called_directly`` is set when a task function is invoked as a plain
    call (``my_task()``) — there is no execution row to refresh then.
    """
    try:
        request = current_task.request
    except AttributeError:  # no task bound: the proxy wraps ``None``
        return None
    if request is None or getattr(request, "called_directly", True):
        return None
    task_id = getattr(request, "id", None)
    return task_id if isinstance(task_id, str) and task_id else None


def heartbeat(*, force: bool = False) -> bool:
    """Tell the stuck sweep this task is still alive.

    Refreshes ``heartbeat_at`` on the current task's execution row, at most
    once per :data:`~background_tasks.constants.HEARTBEAT_MIN_INTERVAL_SECONDS`
    per task unless *force* is set. Call it more often than the task's stuck
    threshold — every loop iteration is fine.

    Returns whether a write was made. Never raises: outside a task it does
    nothing, and a failed write is logged rather than failing the job it is
    reporting on.
    """
    task_id = _current_task_id()
    if task_id is None:
        return False
    now = time.monotonic()
    with _lock:
        last = _last_beat.get(task_id)
        if not force and last is not None and now - last < HEARTBEAT_MIN_INTERVAL_SECONDS:
            return False
        _last_beat[task_id] = now
    try:
        with sync_session() as session:
            session.execute(
                update(TaskExecution)
                .where(
                    TaskExecution.celery_task_id == task_id,
                    # Only a row still ``running``: a heartbeat must not revive
                    # a row the sweep already declared stuck (it may have been
                    # retried since) or rewrite a terminal one.
                    TaskExecution.status == TaskStatus.RUNNING,
                )
                .values(heartbeat_at=now_utc())
            )
    except Exception:
        logger.exception("heartbeat failed for task_id=%s", task_id)
        return False
    return True


def forget_heartbeat(task_id: str | None) -> None:
    """Drop *task_id*'s throttle entry once the task has finished."""
    if task_id:
        with _lock:
            _last_beat.pop(task_id, None)


__all__ = ["forget_heartbeat", "heartbeat"]
