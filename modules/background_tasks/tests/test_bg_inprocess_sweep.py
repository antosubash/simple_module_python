"""Recovery and lifetime of the web process outbox sweeper (#565)."""

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks.constants import OutboxStatus, TaskStatus
from background_tasks.models import OutboxMessage, TaskExecution
from background_tasks.outbox_sweep import start_sweep, stop_sweep
from background_tasks.tasks import purge_old_executions
from simple_module_core.durable_events import event_key, serialize_event
from simple_module_core.events import Event
from simple_module_db.stored_settings import Setting
from simple_module_test import wait_for
from sqlalchemy import select


@pytest.fixture(autouse=True)
def eager_mode(monkeypatch):
    monkeypatch.setenv("SM_BG_TASKS_TASK_ALWAYS_EAGER", "true")


@dataclass
class SweepPing(Event):
    value: int


async def seed(app, *, crashed=False):
    now = datetime.now(UTC)
    row = OutboxMessage(
        event_key=event_key(SweepPing),
        payload=serialize_event(SweepPing(7)),
        handler_name="sweep-test",
        next_attempt_at=now,
        created_at=now,
        status=OutboxStatus.RUNNING if crashed else OutboxStatus.PENDING,
        locked_until=now - timedelta(seconds=60) if crashed else None,
    )
    async with app.state.sm.db.session_factory() as db:
        db.add(row)
        await db.commit()
    return row.id


async def restart_short(app):
    services = app.state.background_tasks
    await stop_sweep(services)
    # Validation stays >= 1 in production; shorten only this test's clock.
    services.settings.outbox_sweep_interval_seconds = 0.05
    start_sweep(
        services,
        app.state.sm.db.session_factory,
        app.state.sm.event_bus,
        app.state.sm.event_bus.durable_transport.policy,
    )
    return services.outbox_sweep_task


@pytest.mark.parametrize("crashed", [False, True])
async def test_eager_sweep_recovers_without_schedule(app, crashed):
    assert app.state.background_tasks.celery.conf.task_always_eager
    assert app.state.background_tasks.outbox_sweep_task is not None
    seen = []

    async def handler(event, ctx):
        seen.append(event.value)

    app.state.sm.event_bus.subscribe_durable(SweepPing, handler, name="sweep-test")
    row_id = await seed(app, crashed=crashed)
    task = await restart_short(app)

    async def delivered():
        async with app.state.sm.db.session_factory() as db:
            row = await db.get(OutboxMessage, row_id)
            return row.status == OutboxStatus.DELIVERED

    await wait_for(delivered, timeout=10)
    await stop_sweep(app.state.background_tasks)
    assert task.done()
    assert seen == [7]


async def test_loop_lifespan_is_idempotent(app):
    services = app.state.background_tasks
    task = services.outbox_sweep_task
    assert task is not None
    start_sweep(
        services,
        app.state.sm.db.session_factory,
        app.state.sm.event_bus,
        app.state.sm.event_bus.durable_transport.policy,
    )
    assert services.outbox_sweep_task is task
    from background_tasks.module import BackgroundTasksModule

    await BackgroundTasksModule().on_shutdown(app)
    assert task.done()
    assert services.outbox_sweep_task is None


def test_transport_import_does_not_load_celery():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import background_tasks.outbox_transport; "
            "assert 'celery' not in sys.modules",
        ],
        check=True,
    )


def test_purge_uses_db_retention(sync_sqlite, monkeypatch):
    from background_tasks.sync_db import get_sync_session_factory, sync_session

    Setting.metadata.create_all(get_sync_session_factory().kw["bind"])

    monkeypatch.delenv("SM_BG_TASKS_RETENTION_DAYS", raising=False)
    with sync_session() as db:
        db.add(Setting(key="background_tasks.retention_days", value="2", value_type="int"))
        db.add(
            TaskExecution(
                task_name="old",
                status=TaskStatus.SUCCESS,
                finished_at=datetime.now(UTC) - timedelta(days=3),
            )
        )
        db.add(
            TaskExecution(
                task_name="recent",
                status=TaskStatus.SUCCESS,
                finished_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    assert purge_old_executions.run() == 1
    with sync_session() as db:
        assert list(db.scalars(select(TaskExecution.task_name))) == ["recent"]


@pytest.mark.postgres
async def test_two_web_loops_deliver_once(app):
    if app.state.sm.db.engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    from background_tasks.outbox_sweep import sweep_loop

    seen = []

    async def handler(event, ctx):
        seen.append(event.value)

    bus = app.state.sm.event_bus
    bus.subscribe_durable(SweepPing, handler, name="sweep-test")
    await stop_sweep(app.state.background_tasks)
    await seed(app)
    loops = [
        asyncio.create_task(
            sweep_loop(app.state.sm.db.session_factory, bus, bus.durable_transport.policy, 0.05)
        )
        for _ in range(2)
    ]
    try:
        await wait_for(lambda: bool(seen), timeout=5)
        await asyncio.sleep(0.15)  # intentional-sleep: window for a duplicate delivery to show up
        assert seen == [7]
    finally:
        for task in loops:
            task.cancel()
        await asyncio.gather(*loops, return_exceptions=True)
