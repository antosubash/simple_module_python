"""Re-enqueueing work: one execution, or a filtered sweep of them.

Split from :mod:`background_tasks.service` because re-enqueueing is the only
thing in this module that writes to the broker, and it is where every
correctness question lives — what may be retried, how many at once, and what
must not happen twice. The read paths have none of those questions.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from simple_module_core.events import EventBus
from simple_module_db import RequestSession
from sqlalchemy import Select, func, select

from background_tasks.constants import RETRY_ALL_BATCH, TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.contracts.schemas import RetryFailedResult
from background_tasks.filters import Conditions, bulk_retry_conditions
from background_tasks.models import TaskExecution

if TYPE_CHECKING:
    from celery import Celery


def claim_query(conditions: Conditions, batch: int) -> Select[tuple[TaskExecution]]:
    """The rows one sweep takes, held for the length of its transaction.

    ``FOR UPDATE SKIP LOCKED`` is what makes two simultaneous sweeps disjoint.
    The guard that is *supposed* to keep a row out of a second sweep —
    :func:`~background_tasks.filters.bulk_retry_conditions` excluding parents
    that already have a child — only starts working once the child row exists,
    and a concurrent sweep reads the same batch long before that. Locking the
    parents makes the second reader skip them instead of publishing the same
    tasks a second time, and the rows stay held until the transaction that
    wrote the children commits, which is the moment the child guard takes over.

    ``skip_locked`` rather than plain ``FOR UPDATE``: a second operator should
    get "nothing left to sweep" immediately, not block behind a 500-row batch.

    SQLite has no row locks and silently emits no clause; it also takes a
    database-wide write lock, so the two sweeps this protects against cannot
    overlap there in the first place.
    """
    return (
        select(TaskExecution)
        .where(*conditions)
        # Oldest first: the queue an operator is unwedging should come back
        # out in the order it went in.
        .order_by(TaskExecution.queued_at.asc().nulls_last())
        .limit(batch)
        .with_for_update(skip_locked=True)
    )


class RetryCoordinator:
    """Sends tasks again and records each fresh attempt.

    The original row is immutable: a retry inserts a *new* ``TaskExecution``
    carrying ``retried_from_id``, so the detail page can show the chain and
    nothing rewrites history.

    Takes a :class:`~simple_module_db.RequestSession` rather than a bare
    ``AsyncSession`` because it announces retries through the session's
    post-commit hook — see :meth:`_announce_after_commit`.
    """

    def __init__(self, db: RequestSession, celery: Celery, event_bus: EventBus) -> None:
        self.db = db
        self.celery = celery
        self.event_bus = event_bus

    async def retry_one(self, row: TaskExecution) -> TaskExecution:
        """Re-enqueue a single execution.

        Publishes inline rather than on a thread: it is one call, and keeping
        it on the event loop keeps Celery's eager mode — which runs the task
        body inside ``send_task`` — on the same thread the signal handlers are
        bound to. The sweep below, which sends hundreds, goes to a thread.
        """
        new_row = self._new_attempt(row, self._publish(row))
        self.db.add(new_row)
        await self.db.flush()
        await self.db.refresh(new_row)
        self._announce_after_commit([(row, new_row)])
        return new_row

    async def retry_failed(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        queue: str | None = None,
        limit: int | None = None,
    ) -> RetryFailedResult:
        """Re-enqueue the retryable executions the current view can see.

        "Failed" is the operator's word for both halves of the set: a stuck
        task is one whose worker died holding it, and it needs the same push.
        Scope comes from :func:`bulk_retry_conditions`, which is the listing's
        own filters plus the two sweep rules.

        Capped at *limit* rows per call (default :data:`RETRY_ALL_BATCH`);
        ``remaining`` says how many eligible rows the cap left behind, so the
        operator knows to press again. The new rows are ``pending`` and their
        parents now have a child, so neither this pass nor the next picks up
        its own work.

        Two operators pressing the button at once used to run every task twice:
        both read the same batch, and the child rows that would have excluded
        it were only written afterwards. :func:`claim_query` locks the batch,
        and the children are written *before* the tasks are published — an
        orphaned ``pending`` row that was never sent is a far cheaper failure
        than a task that ran twice.
        """
        # Read at call time, not bound as a default argument, so the cap has
        # exactly one source of truth that tests and operators can move.
        batch = RETRY_ALL_BATCH if limit is None else limit
        conditions = bulk_retry_conditions(status=status, task_name=task_name, queue=queue)
        if conditions is None:
            return RetryFailedResult(queued=0, remaining=0)

        eligible = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(TaskExecution).where(*conditions)
                )
            ).scalar_one()
        )
        if not eligible:
            return RetryFailedResult(queued=0, remaining=0)

        rows = list((await self.db.execute(claim_query(conditions, batch))).scalars())
        if not rows:
            # Everything eligible is held by a sweep that got here first. Say
            # so rather than reporting an empty queue: the work is moving, just
            # not by this press.
            return RetryFailedResult(queued=0, remaining=eligible)

        # The broker id is reserved here rather than read back from ``send_task``
        # so the row recording the attempt can be written first and still name
        # the task that will carry it. Held as plain strings, not read back off
        # the ORM objects, because the publish below runs on another thread.
        reserved = [(row, str(uuid.uuid4())) for row in rows]
        new_rows = [self._new_attempt(row, task_id) for row, task_id in reserved]
        self.db.add_all(new_rows)
        # One flush for the batch rather than one per row: the round trips are
        # the sweep's real cost, and the rows have no reason to land singly.
        await self.db.flush()

        # One thread for the whole batch. ``send_task`` is a blocking publish,
        # and a few hundred of them inline would stall every other request for
        # the length of the sweep.
        await asyncio.to_thread(
            lambda: [self._publish(row, task_id=task_id) for row, task_id in reserved]
        )

        self._announce_after_commit(list(zip(rows, new_rows, strict=True)))
        return RetryFailedResult(queued=len(rows), remaining=max(0, eligible - len(rows)))

    def _publish(self, row: TaskExecution, task_id: str | None = None) -> str:
        """Send one task to the broker and return its Celery id.

        *task_id* pre-assigns that id, for callers that wrote the row naming it
        before sending. Omitted, the broker assigns one and the caller stamps
        the row with what comes back.

        Blocking — kombu publishes synchronously. Call it off the event loop
        when sending more than one.
        """
        options: dict[str, Any] = {
            "args": list(row.args or []),
            "kwargs": dict(row.kwargs or {}),
            "queue": row.queue,
        }
        if task_id is not None:
            options["task_id"] = task_id
        return self.celery.send_task(row.task_name, **options).id

    def _new_attempt(self, row: TaskExecution, celery_task_id: str) -> TaskExecution:
        """The row recording a fresh attempt at *row*. Not yet flushed."""
        return TaskExecution(
            celery_task_id=celery_task_id,
            task_name=row.task_name,
            status=TaskStatus.PENDING,
            queue=row.queue,
            args=list(row.args or []),
            kwargs=dict(row.kwargs or {}),
            retried_from_id=row.id,
        )

    def _announce_after_commit(
        self, retried: Sequence[tuple[TaskExecution, TaskExecution]]
    ) -> None:
        """Announce each retry once its row is durable. Same event either path.

        Publishing inline told subscribers about a transaction that could still
        roll back — and for a 500-row sweep it told them nothing at all until
        the batch was done, then everything at once. The events are *built*
        here, while the rows are attached and their ids are known, and sent
        from the request's post-commit hook.
        """
        events = [
            TaskRetried(
                original_id=original.id,
                new_id=new_row.id,
                task_name=original.task_name,
            )
            for original, new_row in retried
        ]

        async def publish() -> None:
            for event in events:
                await self.event_bus.publish(event)

        self.db.on_commit(publish)
