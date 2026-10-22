"""Liveness for long-running task bodies (GH #451).

The signal handlers stamp ``heartbeat_at`` when a task starts and when it
finishes — nothing in between. :func:`~background_tasks.tasks.sweep_stuck_tasks`
treats a ``running`` row whose heartbeat is older than the stuck threshold as
a worker that died, and makes it retry-eligible. Without a way to check in
from *inside* the task, every job longer than the threshold was flagged stuck
and could be run a second time while the first was still working.

A task body also reports progress through it (#536): ``heartbeat(progress=(i,
n), message=..., phase=...)``. The latest report is buffered under the same
throttle and written with the next heartbeat; ``i == n`` forces the write.

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
from background_tasks.constants import (
    HEARTBEAT_MIN_INTERVAL_SECONDS,
    PROGRESS_MESSAGE_MAX_LENGTH,
    PROGRESS_PHASE_MAX_LENGTH,
    TaskStatus,
)
from background_tasks.models import TaskExecution
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)

_last_beat: dict[str, float] = {}
# Progress reported but not yet written, per task: the latest report wins.
_pending: dict[str, dict[str, object]] = {}
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


def _progress_values(
    progress: tuple[int, int] | None, message: str | None, phase: str | None
) -> dict[str, object]:
    values: dict[str, object] = {}
    if progress is not None:
        current, total = int(progress[0]), int(progress[1])
        values["progress_current"] = max(current, 0)
        values["progress_total"] = max(total, 0)
    if message is not None:
        values["progress_message"] = message[:PROGRESS_MESSAGE_MAX_LENGTH]
    if phase is not None:
        values["progress_phase"] = phase[:PROGRESS_PHASE_MAX_LENGTH]
    return values


def heartbeat(
    *,
    progress: tuple[int, int] | None = None,
    message: str | None = None,
    phase: str | None = None,
    force: bool = False,
) -> bool:
    """Tell the stuck sweep this task is still alive, optionally with progress.

    Refreshes ``heartbeat_at`` on the current task's execution row, at most
    once per :data:`~background_tasks.constants.HEARTBEAT_MIN_INTERVAL_SECONDS`
    per task unless *force* is set. Call it more often than the task's stuck
    threshold — every loop iteration is fine.

    *progress* is ``(done, total)``; *message* and *phase* are short labels.
    A throttled call keeps the latest of them and the next write carries it;
    reaching ``done == total`` writes immediately so a finished task never
    shows 9/10. None of these columns is audited.

    Returns whether a write was made. Never raises: outside a task it does
    nothing, and a failed write is logged rather than failing the job it is
    reporting on.
    """
    task_id = _current_task_id()
    if task_id is None:
        return False
    try:
        reported = _progress_values(progress, message, phase)
    except (TypeError, ValueError, IndexError):
        logger.warning("ignoring malformed progress %r for task_id=%s", progress, task_id)
        reported = _progress_values(None, message, phase)
    if progress is not None and "progress_current" in reported:
        force = force or reported["progress_current"] == reported["progress_total"]
    now = time.monotonic()
    with _lock:
        pending = {**_pending.get(task_id, {}), **reported}
        last = _last_beat.get(task_id)
        if not force and last is not None and now - last < HEARTBEAT_MIN_INTERVAL_SECONDS:
            if pending:
                _pending[task_id] = pending
            return False
        _last_beat[task_id] = now
        _pending.pop(task_id, None)
    try:
        with sync_session() as session:
            session.execute(
                update(TaskExecution)
                .where(
                    TaskExecution.celery_task_id == task_id,  # ty: ignore[invalid-argument-type]
                    # Only a row still ``running``: a heartbeat must not revive
                    # a row the sweep already declared stuck (it may have been
                    # retried since) or rewrite a terminal one.
                    TaskExecution.status == TaskStatus.RUNNING,  # ty: ignore[invalid-argument-type]
                )
                .values(heartbeat_at=now_utc(), **pending)
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
            _pending.pop(task_id, None)


__all__ = ["forget_heartbeat", "heartbeat"]
