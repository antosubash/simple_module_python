"""Signal-handler helpers shared across :mod:`background_tasks.signals`.

Kept in a separate module so :mod:`.signals` stays under the 300-line cap.
These helpers are intentionally side-effect-free except for the DB write in
``upsert_by_celery_id`` — signal handlers compose them.
"""

from __future__ import annotations

import traceback as tb_mod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from background_tasks.models import TaskExecution


def now_utc() -> datetime:
    return datetime.now(UTC)


def coerce_args_kwargs(args: Any, kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
    """Normalise Celery args/kwargs payloads to JSON-ready shapes.

    Celery sometimes hands us tuples/frozensets that our JSON column can't
    store; also tolerates ``None`` so a partial payload won't wedge the row.
    """
    safe_args: list[Any] = list(args) if args else []
    safe_kwargs: dict[str, Any] = dict(kwargs) if kwargs else {}
    return safe_args, safe_kwargs


def upsert_by_celery_id(
    session: Session,
    *,
    celery_task_id: str | None,
    task_name: str,
    defaults: dict[str, Any],
) -> TaskExecution:
    """Fetch the row for ``celery_task_id``, or create it with ``defaults``.

    Handlers never race on the same row within a worker process — Celery
    serialises per-task signals — so this is upsert-by-read, no advisory
    locks needed.
    """
    row: TaskExecution | None = None
    if celery_task_id:
        stmt = select(TaskExecution).where(TaskExecution.celery_task_id == celery_task_id)
        row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        # Callers sometimes include ``task_name`` in defaults too — let their
        # value win, but ensure a name is always set.
        row_kwargs = {"task_name": task_name, **defaults}
        row = TaskExecution(celery_task_id=celery_task_id, **row_kwargs)
        session.add(row)
    else:
        for key, value in defaults.items():
            setattr(row, key, value)
    return row


def task_name_of(sender: Any, task: Any) -> str:
    """Best-effort resolution of a task's registered name from signal args."""
    return (
        (isinstance(sender, str) and sender)
        or getattr(task, "name", None)
        or getattr(sender, "name", None)
        or "unknown"
    )


def jsonable_result(result: Any) -> dict[str, Any] | None:
    """Wrap arbitrary task results in a JSON-storable shape."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    try:
        return {"value": result}
    except Exception:
        return {"value": repr(result)}


def render_traceback(einfo: Any, exception: BaseException | None) -> str | None:
    """Prefer Celery's pre-formatted traceback; fall back to the live exception."""
    tb = getattr(einfo, "traceback", None)
    if tb:
        return str(tb)
    if exception is not None:
        return "".join(tb_mod.format_exception(type(exception), exception, exception.__traceback__))
    return None
