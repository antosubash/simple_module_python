"""Celery signal handlers that keep the ``TaskExecution`` table in sync.

Each signal writes one row: publish creates ``pending``, prerun flips to
``running`` with a heartbeat, postrun/success/failure/retry/revoked update
the terminal columns. We update an existing row (matched by
``celery_task_id``) so a single task's lifecycle stays on one row instead
of spawning a new row per signal.

Signals are sync — see :mod:`.sync_db` for why we maintain a separate sync
engine, and :mod:`._signal_support` for the shared helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import signals

from background_tasks._signal_support import (
    coerce_args_kwargs,
    jsonable_result,
    now_utc,
    render_traceback,
    task_name_of,
    upsert_by_celery_id,
)
from background_tasks.constants import DEFAULT_QUEUE, TaskStatus
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)


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

    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "task_name": task_name,
                    "status": TaskStatus.PENDING,
                    "queue": routing_key or DEFAULT_QUEUE,
                    "args": args,
                    "kwargs": kwargs,
                    "queued_at": now_utc(),
                },
            )
    except Exception:
        logger.exception("on_task_publish failed for task_id=%s", task_id)


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
    task_name = task_name_of(sender, task)
    args_n, kwargs_n = coerce_args_kwargs(args, kwargs)
    now = now_utc()
    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "task_name": task_name,
                    "status": TaskStatus.RUNNING,
                    "args": args_n,
                    "kwargs": kwargs_n,
                    "started_at": now,
                    "heartbeat_at": now,
                },
            )
    except Exception:
        logger.exception("on_task_prerun failed for task_id=%s", task_id)


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
    task_name = task_name_of(sender, task)
    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={"heartbeat_at": now_utc()},
            )
    except Exception:
        logger.exception("on_task_postrun failed for task_id=%s", task_id)


@signals.task_success.connect
def on_task_success(sender: Any = None, result: Any = None, **_k: Any) -> None:
    task_id = getattr(sender.request, "id", None) if sender is not None else None
    task_name = getattr(sender, "name", None) or "unknown"
    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "status": TaskStatus.SUCCESS,
                    "result": jsonable_result(result),
                    "finished_at": now_utc(),
                    "traceback": None,
                    "exception_type": None,
                },
            )
    except Exception:
        logger.exception("on_task_success failed for task_id=%s", task_id)


@signals.task_failure.connect
def on_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    einfo: Any = None,
    **_k: Any,
) -> None:
    task_name = getattr(sender, "name", None) or "unknown"
    tb = render_traceback(einfo, exception)
    exc_type = type(exception).__name__ if exception is not None else None
    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "status": TaskStatus.FAILED,
                    "traceback": tb,
                    "exception_type": exc_type,
                    "finished_at": now_utc(),
                },
            )
    except Exception:
        logger.exception("on_task_failure failed for task_id=%s", task_id)


@signals.task_retry.connect
def on_task_retry(
    sender: Any = None,
    request: Any = None,
    reason: Any = None,
    **_k: Any,
) -> None:
    task_id = getattr(request, "id", None) if request is not None else None
    task_name = getattr(sender, "name", None) or "unknown"
    retries = int(getattr(request, "retries", 0) or 0)
    try:
        with sync_session() as session:
            row = upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "status": TaskStatus.RETRYING,
                    "retries": retries,
                    "heartbeat_at": now_utc(),
                },
            )
            # Preserve the latest reason for the UI without nulling a
            # previously-captured traceback.
            if reason is not None:
                row.traceback = f"retry: {reason!r}"
    except Exception:
        logger.exception("on_task_retry failed for task_id=%s", task_id)


@signals.task_revoked.connect
def on_task_revoked(sender: Any = None, request: Any = None, **_k: Any) -> None:
    task_id = getattr(request, "id", None) if request is not None else None
    task_name = getattr(sender, "name", None) or "unknown"
    try:
        with sync_session() as session:
            upsert_by_celery_id(
                session,
                celery_task_id=task_id,
                task_name=task_name,
                defaults={
                    "status": TaskStatus.REVOKED,
                    "finished_at": now_utc(),
                },
            )
    except Exception:
        logger.exception("on_task_revoked failed for task_id=%s", task_id)
