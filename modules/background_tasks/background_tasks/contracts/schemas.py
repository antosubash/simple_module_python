"""DTOs returned by the BackgroundTasks admin API / views."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import ConfigDict
from sqlmodel import SQLModel

from background_tasks.constants import TaskStatus


class TaskExecutionListItem(SQLModel):
    """Compact row for the admin listing table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    celery_task_id: str | None = None
    task_name: str
    status: TaskStatus
    queue: str
    retries: int
    worker: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exception_type: str | None = None
    retried_from_id: uuid.UUID | None = None


class TaskExecutionDetail(SQLModel):
    """Full row for the detail page (adds args/kwargs/result/traceback)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    celery_task_id: str | None = None
    task_name: str
    status: TaskStatus
    queue: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    traceback: str | None = None
    exception_type: str | None = None
    worker: str | None = None
    retries: int = 0
    retried_from_id: uuid.UUID | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None


class TaskExecutionListResponse(SQLModel):
    """Paginated response shape used by both the API and Inertia views."""

    items: list[TaskExecutionListItem]
    total: int
    page: int
    per_page: int
    status: TaskStatus | None = None
    task_name: str | None = None
