"""Re-enqueueing work: one execution, or a filtered sweep of them.

Split from :mod:`background_tasks.service` because re-enqueueing is the only
thing in this module that writes to the broker, and it is where every
correctness question lives — what may be retried, how many at once, and what
must not happen twice. The read paths have none of those questions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from simple_module_core.events import EventBus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from background_tasks.constants import RETRY_ALL_BATCH, TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.contracts.schemas import RetryFailedResult
from background_tasks.filters import bulk_retry_conditions
from background_tasks.models import TaskExecution

if TYPE_CHECKING:
    from celery import Celery


class RetryCoordinator:
    """Sends tasks again and records each fresh attempt.

    The original row is immutable: a retry inserts a *new* ``TaskExecution``
    carrying ``retried_from_id``, so the detail page can show the chain and
    nothing rewrites history.
    """

    def __init__(self, db: AsyncSession, celery: Celery, event_bus: EventBus) -> None:
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
        await self._announce(row, new_row)
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

        rows = list(
            (
                await self.db.execute(
                    select(TaskExecution)
                    .where(*conditions)
                    # Oldest first: the queue an operator is unwedging should
                    # come back out in the order it went in.
                    .order_by(TaskExecution.queued_at.asc().nulls_last())
                    .limit(batch)
                )
            ).scalars()
        )

        # One thread for the whole batch. ``send_task`` is a blocking publish,
        # and a few hundred of them inline would stall every other request for
        # the length of the sweep.
        celery_ids = await asyncio.to_thread(lambda: [self._publish(row) for row in rows])

        new_rows = [
            self._new_attempt(row, celery_id)
            for row, celery_id in zip(rows, celery_ids, strict=True)
        ]
        self.db.add_all(new_rows)
        # One flush for the batch rather than one per row: the round trips are
        # the sweep's real cost, and the rows have no reason to land singly.
        await self.db.flush()

        for original, new_row in zip(rows, new_rows, strict=True):
            await self._announce(original, new_row)
        return RetryFailedResult(queued=len(rows), remaining=max(0, eligible - len(rows)))

    def _publish(self, row: TaskExecution) -> str:
        """Send one task to the broker and return its Celery id.

        Blocking — kombu publishes synchronously. Call it off the event loop
        when sending more than one.
        """
        return self.celery.send_task(
            row.task_name,
            args=list(row.args or []),
            kwargs=dict(row.kwargs or {}),
            queue=row.queue,
        ).id

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

    async def _announce(self, original: TaskExecution, new_row: TaskExecution) -> None:
        """Same event whichever path enqueued it — a retry is a retry."""
        await self.event_bus.publish(
            TaskRetried(
                original_id=original.id,
                new_id=new_row.id,
                task_name=original.task_name,
            )
        )
