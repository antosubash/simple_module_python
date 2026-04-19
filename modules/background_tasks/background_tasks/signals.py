"""Celery signal handlers that keep the ``TaskExecution`` table in sync.

Each signal writes one row: publish creates ``pending``, prerun flips to
``running`` with a heartbeat, postrun/success/failure/retry/revoked update
the terminal columns. We update an existing row (matched by
``celery_task_id``) so a single task's lifecycle stays on one row instead
of spawning a new row per signal.

Signals are sync — see :mod:`.sync_db` for why we maintain a separate sync
engine, and :mod:`._signal_support` for the shared helpers.

``TaskFailed`` is also dispatched from :func:`on_task_failure` when an event
bus has been bound via :func:`bind_event_bus` — typically from the web
process's ``on_startup``. In a standalone Celery worker (separate process)
no bus is bound and the publish becomes a no-op; subscribers that need
cross-process notification should consume Celery events or poll the DB
directly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from celery import signals
from simple_module_core.events import EventBus

from background_tasks._signal_support import (
    coerce_args_kwargs,
    jsonable_result,
    now_utc,
    render_traceback,
    task_id_from,
    task_name_of,
    upsert_by_celery_id,
)
from background_tasks.constants import DEFAULT_QUEUE, TaskStatus
from background_tasks.contracts.events import TaskFailed
from background_tasks.models import TaskExecution
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)


_bus: EventBus | None = None
_loop: asyncio.AbstractEventLoop | None = None


def bind_event_bus(bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
    """Bind an event bus + its running loop so signals can publish events.

    Signals fire on the Celery sync thread; `run_coroutine_threadsafe`
    bridges back to ``loop`` so handlers run on the API event loop
    regardless of which thread triggered the signal.
    """
    global _bus, _loop
    _bus = bus
    _loop = loop


def unbind_event_bus() -> None:
    """Drop the bound bus — called from ``on_shutdown`` so tests stay isolated."""
    global _bus, _loop
    _bus = None
    _loop = None


def _publish_from_signal(event: Any) -> None:
    """Dispatch ``event`` onto the bound bus without blocking the signal thread."""
    if _bus is None or _loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(_bus.publish(event), _loop)
    except RuntimeError:
        # Loop has stopped (shutdown race). Swallow — the DB row is already written.
        logger.debug("Event bus loop is not running; skipping %s", type(event).__name__)


def _apply(
    handler: str,
    *,
    celery_task_id: str | None,
    defaults: dict[str, Any],
    after: Callable[[TaskExecution], None] | None = None,
) -> None:
    """Open a sync session, upsert by celery_task_id, log on failure."""
    try:
        with sync_session() as session:
            row = upsert_by_celery_id(session, celery_task_id=celery_task_id, defaults=defaults)
            if after is not None:
                after(row)
    except Exception:
        logger.exception("%s failed for task_id=%s", handler, celery_task_id)


# ── Enqueue ─────────────────────────────────────────────────────


@signals.before_task_publish.connect
def on_task_publish(
    sender: str | None = None,
    headers: dict[str, Any] | None = None,
    body: Any = None,
    routing_key: str | None = None,
    **_kwargs: Any,
) -> None:
    """Record a row the moment a task is pushed onto the broker."""
    task_id = (headers or {}).get("id")
    task_name = sender or (headers or {}).get("task") or "unknown"

    # ``body`` on the publish signal is ``(args, kwargs, options)`` for the
    # standard Celery protocol; guard against edge shapes.
    args_in, kwargs_in = [], {}
    if isinstance(body, list | tuple) and len(body) >= 2:
        args_in, kwargs_in = body[0], body[1]
    args, kwargs = coerce_args_kwargs(args_in, kwargs_in)

    _apply(
        "on_task_publish",
        celery_task_id=task_id,
        defaults={
            "task_name": task_name,
            "status": TaskStatus.PENDING,
            "queue": routing_key or DEFAULT_QUEUE,
            "args": args,
            "kwargs": kwargs,
            "queued_at": now_utc(),
        },
    )


# ── Execution lifecycle ─────────────────────────────────────────


@signals.task_prerun.connect
def on_task_prerun(
    sender: Any = None,
    task_id: str | None = None,
    task: Any = None,
    args: Any = None,
    kwargs: Any = None,
    **_k: Any,
) -> None:
    """Flip the row to ``running`` and start the heartbeat."""
    args_n, kwargs_n = coerce_args_kwargs(args, kwargs)
    now = now_utc()
    _apply(
        "on_task_prerun",
        celery_task_id=task_id,
        defaults={
            "task_name": task_name_of(sender, task),
            "status": TaskStatus.RUNNING,
            "args": args_n,
            "kwargs": kwargs_n,
            "started_at": now,
            "heartbeat_at": now,
        },
    )


@signals.task_postrun.connect
def on_task_postrun(
    sender: Any = None,
    task_id: str | None = None,
    task: Any = None,
    **_k: Any,
) -> None:
    """Refresh the heartbeat on normal completion.

    Terminal status is written by ``task_success`` / ``task_failure`` /
    ``task_retry`` which fire *before* postrun; postrun only refreshes the
    heartbeat so the sweep doesn't immediately flip a just-finished row.
    """
    _apply(
        "on_task_postrun",
        celery_task_id=task_id,
        defaults={"task_name": task_name_of(sender, task), "heartbeat_at": now_utc()},
    )


@signals.task_success.connect
def on_task_success(sender: Any = None, result: Any = None, **_k: Any) -> None:
    _apply(
        "on_task_success",
        celery_task_id=task_id_from(sender=sender),
        defaults={
            "task_name": task_name_of(sender),
            "status": TaskStatus.SUCCESS,
            "result": jsonable_result(result),
            "finished_at": now_utc(),
            "traceback": None,
            "exception_type": None,
        },
    )


@signals.task_failure.connect
def on_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    einfo: Any = None,
    **_k: Any,
) -> None:
    task_name = task_name_of(sender)
    exception_type = type(exception).__name__ if exception is not None else None

    published_id: list[Any] = []

    def _capture_id(row: TaskExecution) -> None:
        published_id.append(row.id)

    _apply(
        "on_task_failure",
        celery_task_id=task_id,
        defaults={
            "task_name": task_name,
            "status": TaskStatus.FAILED,
            "traceback": render_traceback(einfo, exception),
            "exception_type": exception_type,
            "finished_at": now_utc(),
        },
        after=_capture_id,
    )

    if published_id:
        _publish_from_signal(
            TaskFailed(
                task_execution_id=published_id[0],
                task_name=task_name,
                exception_type=exception_type,
            )
        )


@signals.task_retry.connect
def on_task_retry(
    sender: Any = None,
    request: Any = None,
    reason: Any = None,
    **_k: Any,
) -> None:
    def _stamp_reason(row: TaskExecution) -> None:
        # Preserve the latest reason for the UI without nulling a
        # previously-captured traceback.
        if reason is not None:
            row.traceback = f"retry: {reason!r}"

    _apply(
        "on_task_retry",
        celery_task_id=task_id_from(request=request),
        defaults={
            "task_name": task_name_of(sender),
            "status": TaskStatus.RETRYING,
            "retries": int(getattr(request, "retries", 0) or 0),
            "heartbeat_at": now_utc(),
        },
        after=_stamp_reason,
    )


@signals.task_revoked.connect
def on_task_revoked(sender: Any = None, request: Any = None, **_k: Any) -> None:
    _apply(
        "on_task_revoked",
        celery_task_id=task_id_from(request=request),
        defaults={
            "task_name": task_name_of(sender),
            "status": TaskStatus.REVOKED,
            "finished_at": now_utc(),
        },
    )
