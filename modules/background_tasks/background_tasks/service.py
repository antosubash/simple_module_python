"""BackgroundTaskService — admin listing, detail, and retry."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from simple_module_core.events import EventBus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from background_tasks.constants import (
    RETRYABLE_STATUSES,
    TaskStatus,
)
from background_tasks.contracts.events import TaskRetried
from background_tasks.contracts.schemas import (
    TaskExecutionDetail,
    TaskExecutionListItem,
    TaskExecutionListResponse,
)
from background_tasks.models import TaskExecution

if TYPE_CHECKING:
    from celery import Celery


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
        celery: Celery | None,
        event_bus: EventBus,
    ) -> None:
        self.db = db
        self.celery = celery
        self.event_bus = event_bus

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> TaskExecutionListResponse:
        """Return a paginated listing, newest-first, with optional filters."""
        page = max(page, 1)
        per_page = max(1, min(per_page, 200))

        filters = []
        if status is not None:
            filters.append(TaskExecution.status == status)
        if task_name:
            filters.append(TaskExecution.task_name.ilike(f"%{task_name}%"))

        base = select(TaskExecution)
        for f in filters:
            base = base.where(f)

        count_query = select(func.count()).select_from(TaskExecution)
        for f in filters:
            count_query = count_query.where(f)
        total = (await self.db.execute(count_query)).scalar() or 0

        query = (
            base.order_by(TaskExecution.queued_at.desc().nulls_last())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = (await self.db.execute(query)).scalars().all()

        return TaskExecutionListResponse(
            items=[TaskExecutionListItem.model_validate(r) for r in rows],
            total=total,
            page=page,
            per_page=per_page,
            status=status,
            task_name=task_name,
        )

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

        # ``row.status`` is a plain string when loaded from SQLite (the
        # column is VARCHAR), a TaskStatus when set via the model. StrEnum
        # compares equal to its string value either way.
        if row.status not in RETRYABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Task execution status is {str(row.status)!r}; "
                    "only failed or stuck tasks can be retried."
                ),
            )

        if self.celery is None:
            # Only happens if on_startup hasn't run — e.g. in a test that
            # instantiates the service without wiring Celery. Fail loudly
            # rather than silently swallowing the retry.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Celery is not initialized; cannot enqueue retry.",
            )

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

        return TaskExecutionDetail.model_validate(new_row)
