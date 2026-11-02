"""The Celery side of the outbox: task bodies, worker engine, purge, beat (GH #459)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks import outbox_worker, sync_db
from background_tasks.celery_app import build_celery
from background_tasks.constants import (
    BEAT_SWEEP_OUTBOX,
    INTERNAL_TASK_SWEEP_OUTBOX,
    OutboxStatus,
)
from background_tasks.models import OutboxMessage
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.tasks import dispatch_outbox, purge_old_executions, sweep_outbox
from simple_module_core import DurableContext
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event, EventBus
from simple_module_db import current_tenant_id
from sqlalchemy import select


@dataclass
class ThumbnailWanted(Event):
    file_id: uuid.UUID


@pytest.fixture
def worker_bus(sync_sqlite):
    """A bus the task bodies dispatch with, as if built by the worker."""
    bus = EventBus()
    outbox_worker.reset_worker_state()
    outbox_worker.use_bus(bus)
    yield bus
    outbox_worker.reset_worker_state()


def _insert(*, handler: str, status: OutboxStatus = OutboxStatus.PENDING, **extra) -> uuid.UUID:
    now = datetime.now(UTC)
    fields = {"next_attempt_at": now, "created_at": now, **extra}
    row = OutboxMessage(
        event_key=event_key(ThumbnailWanted),
        payload=serialize_event(ThumbnailWanted(file_id=uuid.uuid4())),
        handler_name=handler,
        status=status,
        **fields,
    )
    with sync_db.sync_session() as session:
        session.add(row)
    return row.id


def _row(row_id: uuid.UUID) -> OutboxMessage | None:
    with sync_db.sync_session() as session:
        return session.execute(
            select(OutboxMessage).where(OutboxMessage.id == row_id)
        ).scalar_one_or_none()


def test_dispatch_task_delivers_on_the_worker_engine(worker_bus) -> None:
    seen: list[tuple[uuid.UUID, int, str | None]] = []

    async def handler(event: ThumbnailWanted, ctx: DurableContext) -> None:
        seen.append((event.file_id, ctx.attempt, current_tenant_id.get()))

    name = worker_bus.subscribe_durable(ThumbnailWanted, handler)
    row_id = _insert(handler=name, tenant_id="acme")

    summary = dispatch_outbox([str(row_id)])

    assert summary["delivered"] == 1
    assert [(attempt, tenant) for _, attempt, tenant in seen] == [(1, "acme")]
    row = _row(row_id)
    assert row is not None and row.status == OutboxStatus.DELIVERED


async def test_task_body_runs_from_inside_a_running_loop(worker_bus) -> None:
    """Eager Celery inside the web process calls the task on the loop's thread."""

    async def handler(event: ThumbnailWanted, ctx: DurableContext) -> None: ...

    name = worker_bus.subscribe_durable(ThumbnailWanted, handler)
    _insert(handler=name)

    assert sweep_outbox()["delivered"] == 1


def test_sweep_task_only_takes_due_rows(worker_bus) -> None:
    async def handler(event: ThumbnailWanted, ctx: DurableContext) -> None: ...

    name = worker_bus.subscribe_durable(ThumbnailWanted, handler)
    later = _insert(handler=name, next_attempt_at=datetime.now(UTC) + timedelta(hours=1))
    now_id = _insert(handler=name)

    assert sweep_outbox()["delivered"] == 1
    assert _row(now_id).status == OutboxStatus.DELIVERED
    assert _row(later).status == OutboxStatus.PENDING


def test_worker_builds_its_bus_from_installed_modules(sync_sqlite) -> None:
    outbox_worker.reset_worker_state()
    try:
        bus = outbox_worker.worker_bus()
        assert isinstance(bus, EventBus)
        assert outbox_worker.worker_bus() is bus  # cached per process
    finally:
        outbox_worker.reset_worker_state()


def test_async_url_matches_the_sync_engine(monkeypatch) -> None:
    sync_db.dispose_sync_engine()
    sync_db.set_database_url("postgresql+asyncpg://u:p@db/app")
    try:
        assert sync_db.async_database_url() == "postgresql+asyncpg://u:p@db/app"
    finally:
        sync_db.dispose_sync_engine()
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite:///./x.db")
    assert sync_db.async_database_url() == "sqlite+aiosqlite:///./x.db"
    monkeypatch.setenv("SM_DATABASE_URL", "postgresql://u@h/d")
    assert sync_db.async_database_url() == "postgresql+asyncpg://u@h/d"


def test_purge_removes_old_delivered_rows_only(sync_sqlite, monkeypatch) -> None:
    monkeypatch.setenv("SM_BG_TASKS_RETENTION_DAYS", "7")
    old = datetime.now(UTC) - timedelta(days=8)
    old_delivered = _insert(handler="h", status=OutboxStatus.DELIVERED, delivered_at=old)
    fresh_delivered = _insert(
        handler="h", status=OutboxStatus.DELIVERED, delivered_at=datetime.now(UTC)
    )
    old_dead = _insert(handler="h", status=OutboxStatus.DEAD, created_at=old)

    purge_old_executions()

    assert _row(old_delivered) is None
    assert _row(fresh_delivered) is not None
    assert _row(old_dead) is not None


def test_beat_sweeps_the_outbox_on_its_interval() -> None:
    celery = build_celery(BackgroundTasksSettings(outbox_sweep_interval_seconds=45))
    entry = celery.conf.beat_schedule[BEAT_SWEEP_OUTBOX]
    assert entry["task"] == INTERNAL_TASK_SWEEP_OUTBOX
    assert entry["schedule"].run_every.total_seconds() == 45
