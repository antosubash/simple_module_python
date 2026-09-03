"""DTOs returned by the BackgroundTasks admin API / views."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import ConfigDict
from sqlmodel import SQLModel

from background_tasks.constants import TaskStatus


class TaskExecutionListItem(SQLModel):
    """Compact row for the admin listing table.

    Carries ``args``/``kwargs`` even though the table never renders them: the
    retry confirm opens straight from a row and has to show the payload it is
    about to re-enqueue. Re-running a bad payload just fails the same way, so
    the operator needs to read it *before* confirming, not on a second page.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    celery_task_id: str | None = None
    task_name: str
    status: TaskStatus
    queue: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
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
    queue: str | None = None


class RetryFailedResult(SQLModel):
    """How many executions a bulk retry actually re-enqueued.

    The caller cannot compute this: the endpoint decides which statuses count
    as retryable, so the number has to come back from the action itself rather
    than be inferred from whatever the screen was showing.
    """

    queued: int


class WorkerInfo(SQLModel):
    """One Celery worker as reported by ``celery.control.inspect()``."""

    hostname: str
    online: bool
    queues: list[str] = []
    active_task_count: int = 0
    pool_size: int | None = None
    total_processed: int | None = None
    software: str | None = None
    # Seconds since this worker process started, as it reports them. ``None``
    # for a worker that never answered ``stats()`` — an offline worker has no
    # uptime to claim, and zero would read as "just restarted".
    uptime_seconds: float | None = None


class WorkerSnapshot(SQLModel):
    """Point-in-time picture of every worker known to the broker."""

    broker_reachable: bool
    polled_at: datetime
    workers: list[WorkerInfo] = []
    error: str | None = None
