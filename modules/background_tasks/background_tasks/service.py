"""BackgroundTaskService — admin listing, detail, and retry."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from simple_module_core.events import EventBus
from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import ColumnElement, Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from background_tasks.constants import RETRYABLE_STATUSES, TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.contracts.schemas import (
    TaskExecutionDetail,
    TaskExecutionListItem,
    TaskExecutionListResponse,
)
from background_tasks.models import TaskExecution

if TYPE_CHECKING:
    from celery import Celery

# Declared out here because ``BackgroundTaskService.list`` shadows the builtin
# inside the class body, so a ``list[...]`` annotation on a method resolves to
# the method rather than to the type.
Conditions = list["ColumnElement[bool]"]
QueueNames = list[str]


class BackgroundTaskService:
    """List, fetch, and retry task executions.

    The service treats the DB as the system of record and the Celery app
    as pure transport — ``retry`` loads the original row, enqueues a new
    Celery task with the same args/kwargs, and inserts a fresh
    ``TaskExecution`` linked to the original via ``retried_from_id``.
    """

    def __init__(
        self,
        db: AsyncSession,
        celery: Celery,
        event_bus: EventBus,
    ) -> None:
        self.db = db
        self.celery = celery
        self.event_bus = event_bus

    def _filters(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        queue: str | None = None,
    ) -> Conditions:
        """The three axes the executions screen filters on, as SQL conditions.

        Shared by the listing, the strip counts and the bulk retry so they can
        never disagree about what "the current view" means — a bulk action
        scoped differently from the table it sits above is how an operator ends
        up re-enqueueing rows they never saw.
        """
        conditions: Conditions = []
        if status is not None:
            conditions.append(TaskExecution.status == status)
        if task_name:
            conditions.append(
                TaskExecution.task_name.ilike(
                    like_contains_pattern(task_name), escape=LIKE_ESCAPE_CHAR
                )
            )
        if queue:
            conditions.append(TaskExecution.queue == queue)
        return conditions

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        queue: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> TaskExecutionListResponse:
        """Return a paginated listing, newest-first, with optional filters."""
        page = max(page, 1)
        per_page = max(1, min(per_page, 200))

        conditions = self._filters(status=status, task_name=task_name, queue=queue)

        # A window-function total lets us fetch the page and the count in a
        # single round trip. SQLAlchemy's ``AsyncSession`` serialises calls on
        # one connection, so ``asyncio.gather`` wouldn't help here.
        async def fetch(p: int) -> tuple[Sequence[Row[tuple[TaskExecution, int]]], int]:
            total_col = func.count().over().label("_total")
            query = (
                select(TaskExecution, total_col)
                .where(*conditions)
                .order_by(TaskExecution.queued_at.desc().nulls_last())
                .offset((p - 1) * per_page)
                .limit(per_page)
            )
            rows = (await self.db.execute(query)).all()
            return rows, (int(rows[0][1]) if rows else 0)

        rows, total = await fetch(page)
        if not rows and page > 1:
            # The window-function total only rides along on a row that's
            # actually returned, so a page past the end (stale bookmark, a
            # manually-edited ?page=) can't self-report the real total — it
            # looks identical to "there are no rows at all". Count for real,
            # clamp to the last valid page, and refetch so callers never see
            # a false "nothing exists" for a query that has rows elsewhere.
            count_query = select(func.count()).select_from(TaskExecution).where(*conditions)
            real_total = int((await self.db.execute(count_query)).scalar_one())
            if real_total:
                page = max(1, -(-real_total // per_page))  # ceil division
                rows, total = await fetch(page)

        items = [TaskExecutionListItem.model_validate(row[0]) for row in rows]

        return TaskExecutionListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            status=status,
            task_name=task_name,
            queue=queue,
        )

    async def status_counts(
        self, *, task_name: str | None = None, queue: str | None = None
    ) -> dict[str, int]:
        """Count executions per status for the ops strip above the table.

        Deliberately ignores the status filter — the strip is how the operator
        picks a status, so it has to keep showing the ones they aren't looking
        at. It does honour ``task_name`` and ``queue``, which are separate axes:
        the counts describe the same result set the table is paging through.

        Statuses with no rows are omitted; callers fill in zeros.
        """
        query = (
            select(TaskExecution.status, func.count().label("n"))
            .where(*self._filters(task_name=task_name, queue=queue))
            .group_by(TaskExecution.status)
        )

        rows = (await self.db.execute(query)).all()
        # `status` is a TaskStatus (StrEnum) on Postgres but comes back as a
        # plain str on SQLite; normalise so the JSON keys match either way.
        return {str(getattr(row[0], "value", row[0])): int(row[1]) for row in rows}

    async def success_count_since(
        self,
        *,
        hours: int = 24,
        task_name: str | None = None,
        queue: str | None = None,
    ) -> int:
        """Successes that *finished* inside the window.

        Every other tile is an all-time total, which says nothing about whether
        work is flowing now: a queue that succeeded ten thousand times last
        year and nothing since reads exactly like a healthy one. ``finished_at``
        is the basis rather than ``queued_at`` because the tile claims a
        completed outcome — a long job queued yesterday and finished a minute
        ago is part of today's throughput, not yesterday's.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        query = (
            select(func.count())
            .select_from(TaskExecution)
            .where(
                *self._filters(status=TaskStatus.SUCCESS, task_name=task_name, queue=queue),
                TaskExecution.finished_at.is_not(None),
                TaskExecution.finished_at >= cutoff,
            )
        )
        return int((await self.db.execute(query)).scalar_one())

    async def queues(self) -> QueueNames:
        """Every queue that has actually been used, for the queue dropdown.

        Read from the executions themselves rather than from settings: settings
        know the default queue this app publishes to, not the queues a module
        or a worker actually routed work through, and the dropdown exists to
        get an operator to rows that exist.
        """
        query = select(TaskExecution.queue).distinct().order_by(TaskExecution.queue)
        return [q for q in (await self.db.execute(query)).scalars() if q]

    async def get(self, execution_id: uuid.UUID) -> TaskExecutionDetail | None:
        row = await self.db.get(TaskExecution, execution_id)
        if row is None:
            return None
        return TaskExecutionDetail.model_validate(row)

    async def retry(self, execution_id: uuid.UUID) -> TaskExecutionDetail:
        """Re-enqueue a failed or stuck task.

        The original row is immutable; we insert a new ``TaskExecution`` row
        carrying ``retried_from_id`` so the detail page can show the chain.
        """
        row = await self.db.get(TaskExecution, execution_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Task execution not found")

        if row.status not in RETRYABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Task execution status is {str(row.status)!r}; "
                    "only failed or stuck tasks can be retried."
                ),
            )

        new_row = await self._enqueue_retry(row)
        return TaskExecutionDetail.model_validate(new_row)

    async def retry_failed(
        self, *, status: TaskStatus | None = None, queue: str | None = None
    ) -> int:
        """Re-enqueue every retryable execution the current view can see.

        "Failed" is the operator's word for both halves of the set: a stuck
        task is one whose worker died holding it, and it needs exactly the same
        push. A status filter *narrows* that set rather than widening it, so
        pressing the button while looking at ``running`` queues nothing — the
        button can never reach past what is on screen.

        The new rows are ``pending``, so this pass cannot pick up its own work.
        """
        wanted = RETRYABLE_STATUSES if status is None else RETRYABLE_STATUSES & {status}
        if not wanted:
            return 0

        query = (
            select(TaskExecution)
            .where(
                TaskExecution.status.in_(sorted(wanted)),
                *self._filters(queue=queue),
            )
            # Oldest first: the queue an operator is unwedging should come back
            # out in the order it went in.
            .order_by(TaskExecution.queued_at.asc().nulls_last())
        )
        rows = list((await self.db.execute(query)).scalars())
        for row in rows:
            await self._enqueue_retry(row)
        return len(rows)

    async def _enqueue_retry(self, row: TaskExecution) -> TaskExecution:
        """Send one task again and record the new attempt.

        Shared by the single and bulk retries so a row re-enqueued from the
        header button is indistinguishable from one retried through its own
        dialog — same chain, same event, same history.
        """
        async_result = self.celery.send_task(
            row.task_name,
            args=list(row.args or []),
            kwargs=dict(row.kwargs or {}),
            queue=row.queue,
        )

        new_row = TaskExecution(
            celery_task_id=async_result.id,
            task_name=row.task_name,
            status=TaskStatus.PENDING,
            queue=row.queue,
            args=list(row.args or []),
            kwargs=dict(row.kwargs or {}),
            retried_from_id=row.id,
        )
        self.db.add(new_row)
        await self.db.flush()
        await self.db.refresh(new_row)

        await self.event_bus.publish(
            TaskRetried(
                original_id=row.id,
                new_id=new_row.id,
                task_name=row.task_name,
            )
        )
        return new_row
