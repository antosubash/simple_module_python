"""Publish to the broker only once the transaction that justifies it commits.

A task enqueued inside a transaction races that transaction: the worker can
pick the message up before the row it refers to is visible (eager mode runs
it *inside* ``send_task``), and if the commit then fails the task is already
queued against nothing. Both are fixed the same way — hold the publish until
the commit has landed, and drop it if the transaction rolls back (GH #452).

Two delivery paths, picked per session:

- **A request's session** (``get_db``) — the publish goes through
  :meth:`~simple_module_db.RequestSession.on_commit`, which the framework runs
  after the request's commit and before the response is sent, and discards on
  rollback or commit failure.
- **Any other session** — a worker's sync session, a CLI script's own
  ``async with session.begin()`` — has nobody to run ``on_commit`` callbacks,
  so the publish hangs off SQLAlchemy's ``after_commit`` event instead and is
  dropped when the outermost transaction ends without committing.

The broker id is reserved up front and returned, so the caller can write it
onto its own row in the same transaction: the row names the task before the
task exists, never the other way round.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from celery import current_app
from simple_module_db import RequestSession, bind_current_tenant, mark_written
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

logger = logging.getLogger(__name__)

type Publish = Callable[[], object]

_PENDING_KEY = "background_tasks_after_commit"
_HOOKED_KEY = "background_tasks_after_commit_hooked"


def enqueue_after_commit(db: AsyncSession | Session, task: Any, *args: Any, **kwargs: Any) -> str:
    """Send *task* once *db*'s transaction commits; never if it rolls back.

    *task* is a Celery task (``send_receipt``), a signature
    (``send_receipt.s().set(queue="mail")``, for routing options), or a
    registered task name. ``*args`` / ``**kwargs`` are the task's own
    arguments. Returns the Celery task id the message will carry.

    Publishes as the tenant bound *now*, so a task enqueued in a request runs
    for that request's tenant even when the commit happens elsewhere.
    """
    task_id = str(uuid.uuid4())

    def publish() -> None:
        if isinstance(task, str):
            current_app.send_task(task, args=list(args), kwargs=kwargs, task_id=task_id)
        else:
            task.apply_async(args=args, kwargs=kwargs, task_id=task_id)

    after_commit(db, [bind_current_tenant(publish)])
    return task_id


def after_commit(
    db: AsyncSession | Session, publishes: Sequence[Publish], *, offload: bool = False
) -> None:
    """Run each of *publishes* after *db* commits, in order. Internal.

    *offload* sends the batch to a thread when the request path runs it: kombu
    publishes block, and hundreds of them on the event loop stall every other
    request. Left off for a single publish so Celery's eager mode — which runs
    the task body inside the publish — stays on the loop's thread. One failed
    publish is logged and does not stop the rest: the rows are already
    committed, and an unsent ``pending`` row is visible and retryable.
    """
    batch = list(publishes)
    if isinstance(db, RequestSession) and SESSION_START_KEY in db.info:
        # A request that wrote nothing else is rolled back and its ``on_commit``
        # callbacks discarded, which would drop this publish silently. Queueing a
        # task is itself work that must survive to the commit.
        mark_written(db)
        if offload:
            db.on_commit(lambda: asyncio.to_thread(_run_all, batch))
        else:
            db.on_commit(lambda: _run_all(batch))
        return
    sync = db.sync_session if isinstance(db, AsyncSession) else db
    sync.info.setdefault(_PENDING_KEY, []).extend(batch)
    _hook(sync)


def _run_all(batch: Sequence[Publish]) -> None:
    for publish in batch:
        try:
            publish()
        except Exception:
            logger.exception("background_tasks.after_commit.publish_failed")


def _hook(session: Session) -> None:
    """Attach the commit/rollback listeners to *session* once."""
    if session.info.get(_HOOKED_KEY):
        return
    session.info[_HOOKED_KEY] = True

    def on_commit(sess: Session) -> None:
        _run_all(sess.info.pop(_PENDING_KEY, []))

    def on_end(sess: Session, transaction: SessionTransaction) -> None:
        # ``after_commit`` already took the batch on the commit path; anything
        # still queued when the outermost transaction ends was rolled back.
        if transaction.parent is None:
            sess.info.pop(_PENDING_KEY, None)

    event.listen(session, "after_commit", on_commit)
    event.listen(session, "after_transaction_end", on_end)


__all__ = ["enqueue_after_commit"]
