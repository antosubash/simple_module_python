"""SQLModel tables for the BackgroundTasks module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import JSON, Column, Index, String
from sqlmodel import Field

from background_tasks.constants import (
    DEFAULT_QUEUE,
    MODULE_NAME,
    TABLE_TASK_EXECUTION,
    TaskStatus,
)

Base = create_module_base(MODULE_NAME)


class TaskExecution(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Persistent record of a single Celery task execution.

    We keep our own row (separate from Celery's volatile result backend)
    because the admin UI needs stable history, retried-from chains, and a
    "stuck since" timestamp that Celery's state machine doesn't model.
    """

    __tablename__ = TABLE_TASK_EXECUTION

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Celery's own UUID for the running task. Nullable because we create the
    # row *before* enqueue in the retry flow, then stamp it on send.
    celery_task_id: str | None = Field(default=None, index=True, max_length=64)

    task_name: str = Field(index=True, max_length=255)
    # Stored as a plain string (the enum's ``value``) rather than a native
    # SQL ENUM so autogenerate produces a VARCHAR column and Postgres
    # doesn't own a ``taskstatus`` type that we'd need a separate migration
    # to evolve.
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=Column(String(20), index=True, nullable=False, default=TaskStatus.PENDING.value),
    )
    queue: str = Field(default=DEFAULT_QUEUE, max_length=64)

    args: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    kwargs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    traceback: str | None = None
    exception_type: str | None = Field(default=None, max_length=255)

    worker: str | None = Field(default=None, max_length=255)
    retries: int = 0

    # Self-reference so the UI can show "retried from <original>" chains.
    retried_from_id: uuid.UUID | None = Field(
        default=None,
        foreign_key=f"{TABLE_TASK_EXECUTION}.id",
        index=True,
    )

    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Heartbeat is refreshed on every signal that touches a running task.
    # `stuck_after_seconds` older than ``now`` ⇒ `sweep_stuck_tasks` flips
    # the row to `stuck`.
    heartbeat_at: datetime | None = None

    __table_args__ = (
        Index(
            "ix_background_tasks_task_execution_status_queued",
            "status",
            "queued_at",
        ),
    )
