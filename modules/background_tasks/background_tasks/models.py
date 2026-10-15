"""SQLModel tables for the BackgroundTasks module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from simple_module_db.types import AwareDateTime
from sqlalchemy import JSON, Column, Index, String
from sqlmodel import Field

from background_tasks.constants import (
    DEFAULT_QUEUE,
    MODULE_NAME,
    OUTBOX_KEY_MAX_LENGTH,
    TABLE_OUTBOX,
    TABLE_TASK_EXECUTION,
    TENANT_ID_MAX_LENGTH,
    OutboxStatus,
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

    # The tenant the task was published for; NULL for beat and other platform
    # publishes. Deliberately not MultiTenantMixin: those rows have no tenant
    # and strict mode would raise on their insert. The admin screens are
    # platform-wide and filter on this column.
    tenant_id: str | None = Field(default=None, index=True, max_length=TENANT_ID_MAX_LENGTH)

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
        Index(
            "ix_background_tasks_task_execution_tenant_status_queued",
            "tenant_id",
            "status",
            "queued_at",
        ),
    )


class OutboxMessage(Base, table=True):  # ty: ignore[unsupported-base]
    """One durable event awaiting delivery to one durable handler (GH #459).

    Written in the publisher's transaction by ``OutboxTransport.enqueue``, so a
    rollback leaves no row. ``attempts`` is incremented when a worker claims the
    row and doubles as the claim's fencing token: the worker marks the row
    delivered only while ``attempts`` still equals what it claimed with.

    ``tenant_id`` is a plain column, not ``MultiTenantMixin``, for the same
    reason as ``TaskExecution``: the outbox is platform plumbing read across
    tenants by the dispatcher and the admin screen, and platform publishes
    carry no tenant. The handler itself runs inside ``tenant_context(tenant_id)``.
    """

    __tablename__ = TABLE_OUTBOX

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_key: str = Field(max_length=OUTBOX_KEY_MAX_LENGTH)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    handler_name: str = Field(max_length=OUTBOX_KEY_MAX_LENGTH)
    tenant_id: str | None = Field(default=None, index=True, max_length=TENANT_ID_MAX_LENGTH)
    status: OutboxStatus = Field(
        default=OutboxStatus.PENDING,
        sa_column=Column(String(20), nullable=False, default=OutboxStatus.PENDING.value),
    )
    attempts: int = Field(default=0)
    next_attempt_at: datetime = Field(sa_type=AwareDateTime(), nullable=False)
    # End of the current claim's lease; NULL unless ``running``.
    locked_until: datetime | None = Field(default=None, sa_type=AwareDateTime())
    last_error: str | None = Field(default=None)
    created_at: datetime = Field(sa_type=AwareDateTime(), nullable=False)
    delivered_at: datetime | None = Field(default=None, sa_type=AwareDateTime())

    __table_args__ = (
        # The claim: due pending rows, oldest first.
        Index("ix_background_tasks_outbox_status_next_attempt", "status", "next_attempt_at"),
        # Lease reclaim and the delivered-rows purge.
        Index("ix_background_tasks_outbox_status_locked", "status", "locked_until"),
        Index("ix_background_tasks_outbox_status_delivered", "status", "delivered_at"),
    )
