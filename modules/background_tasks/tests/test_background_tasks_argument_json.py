"""Typed Celery arguments survive tracking and history retries (#754)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from background_tasks import sync_db
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.retry_service import RetryCoordinator
from background_tasks.signals import on_task_publish, on_task_success
from celery import Celery
from simple_module_core.events import EventBus
from sqlalchemy import select

VALUES = [datetime(2026, 1, 1, tzinfo=UTC), UUID(int=1), Decimal("1.25")]


@pytest.fixture
def celery_app():
    with Celery(
        "arguments", broker="memory://", backend="cache+memory://", set_as_current=False
    ) as app:
        app.conf.update(
            task_always_eager=True, task_eager_propagates=True, sm_execution_tracking="full"
        )
        yield app


def test_typed_arguments_track_actual_success(sync_sqlite, celery_app):
    @celery_app.task(name="arguments.job")
    def job(*args, **kwargs):
        assert list(args) == VALUES
        assert kwargs == {"values": VALUES}
        return True

    result = job.apply_async(args=VALUES, kwargs={"values": VALUES})
    assert result.successful()
    with sync_db.sync_session() as session:
        row = session.execute(select(TaskExecution)).scalar_one()
        assert row.status == TaskStatus.SUCCESS
        assert row.args[0] == {"__type__": "datetime", "__value__": "2026-01-01T00:00:00+00:00"}
        assert row.kwargs["values"] == row.args


@pytest.mark.parametrize("path", ["publish", "request"])
def test_each_metadata_path_persists_typed_arguments(sync_sqlite, celery_app, path):
    @celery_app.task(name="arguments.metadata")
    def job():
        pass

    if path == "publish":
        # Publish signals use the current app rather than a task instance.
        from celery import current_app

        previous = current_app._get_current_object()
        celery_app.set_current()
        try:
            on_task_publish(
                sender=job.name, headers={"id": "typed"}, body=(VALUES, {"values": VALUES}, {})
            )
        finally:
            previous.set_current()
    else:
        job.push_request(id="typed", args=VALUES, kwargs={"values": VALUES})
        try:
            on_task_success(sender=job, result=True)
        finally:
            job.pop_request()
    with sync_db.sync_session() as session:
        row = session.execute(select(TaskExecution)).scalar_one()
        assert row.args[0]["__type__"] == "datetime"
        assert row.kwargs["values"] == row.args


def test_history_retry_decodes_typed_arguments(sync_sqlite, celery_app, monkeypatch):
    @celery_app.task(name="arguments.retry")
    def job(value, *, amount, identity):
        assert isinstance(value, datetime)
        assert value == VALUES[0]
        assert isinstance(amount, Decimal)
        assert amount == VALUES[2]
        assert isinstance(identity, UUID)
        assert identity == VALUES[1]
        return True

    celery_app.conf.task_always_eager = False
    send_task = celery_app.send_task

    def send(name, **options):
        assert isinstance(options["args"][0], datetime)
        assert isinstance(options["kwargs"]["amount"], Decimal)
        return send_task(name, **options)

    monkeypatch.setattr(celery_app, "send_task", send)
    row = TaskExecution(
        task_name=job.name,
        args=[
            {
                "__type__": "datetime",
                "__value__": "2026-01-01T00:00:00+00:00",
            }
        ],
        status=TaskStatus.FAILED,
        kwargs={
            "amount": {"__type__": "decimal", "__value__": "1.25"},
            "identity": {
                "__type__": "uuid",
                "__value__": {"hex": "00000000000000000000000000000001"},
            },
        },
    )
    with sync_db.sync_session() as session:
        session.add(row)
    with sync_db.sync_session() as session:
        row = session.execute(select(TaskExecution)).scalar_one()
    coordinator = RetryCoordinator(None, celery_app, EventBus())
    publish = coordinator._publisher(row, "retry-id")
    publish()
    # send_task publishes to the broker even in eager mode; execute the payload locally.
    with celery_app.connection_for_read() as connection:
        queue = connection.SimpleQueue(row.queue)
        try:
            message = queue.get(block=False)
            args, kwargs, _ = message.payload
            assert job.apply(args=args, kwargs=kwargs, throw=True).successful()
            message.ack()
        finally:
            queue.clear()
            queue.close()
