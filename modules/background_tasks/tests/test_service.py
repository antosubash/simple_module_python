"""Unit tests for BackgroundTaskService — list, get, retry logic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from background_tasks.constants import TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.models import TaskExecution
from background_tasks.service import BackgroundTaskService
from fastapi import HTTPException
from simple_module_core.events import EventBus
from sqlalchemy.ext.asyncio import AsyncSession


def _make_row(
    *,
    task_name: str = "demo.task",
    status: TaskStatus = TaskStatus.FAILED,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    queue: str = "default",
    queued_at: datetime | None = None,
) -> TaskExecution:
    return TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name=task_name,
        status=status,
        queue=queue,
        args=args or [],
        kwargs=kwargs or {},
        queued_at=queued_at or datetime.now(UTC),
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_celery() -> MagicMock:
    celery = MagicMock(name="Celery")
    celery.send_task.return_value.id = "new-celery-id-123"
    return celery


@pytest.fixture
def service(
    db_session: AsyncSession, event_bus: EventBus, mock_celery: MagicMock
) -> BackgroundTaskService:
    return BackgroundTaskService(db=db_session, celery=mock_celery, event_bus=event_bus)


class TestList:
    async def test_returns_paginated_rows_newest_first(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        now = datetime.now(UTC)
        older = _make_row(task_name="demo.a", queued_at=now - timedelta(minutes=5))
        newer = _make_row(task_name="demo.b", queued_at=now)
        db_session.add_all([older, newer])
        await db_session.flush()

        resp = await service.list()
        assert resp.total == 2
        assert [i.task_name for i in resp.items] == ["demo.b", "demo.a"]

    async def test_filters_by_status(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        db_session.add_all(
            [
                _make_row(task_name="demo.ok", status=TaskStatus.SUCCESS),
                _make_row(task_name="demo.bad", status=TaskStatus.FAILED),
            ]
        )
        await db_session.flush()

        resp = await service.list(status=TaskStatus.FAILED)
        assert [i.task_name for i in resp.items] == ["demo.bad"]

    async def test_filters_by_task_name_substring(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        db_session.add_all(
            [
                _make_row(task_name="orders.send_receipt"),
                _make_row(task_name="mailer.send_invite"),
            ]
        )
        await db_session.flush()

        resp = await service.list(task_name="receipt")
        assert [i.task_name for i in resp.items] == ["orders.send_receipt"]


class TestGet:
    async def test_returns_none_for_missing_id(self, service: BackgroundTaskService):
        assert await service.get(uuid.uuid4()) is None

    async def test_returns_detail_for_existing_row(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        row = _make_row(args=[1, "two"], kwargs={"three": 3})
        db_session.add(row)
        await db_session.flush()
        await db_session.refresh(row)

        detail = await service.get(row.id)
        assert detail is not None
        assert detail.args == [1, "two"]
        assert detail.kwargs == {"three": 3}


class TestRetry:
    async def test_retry_failed_task_enqueues_and_creates_row(
        self,
        db_session: AsyncSession,
        service: BackgroundTaskService,
        mock_celery: MagicMock,
        event_bus: EventBus,
    ):
        received: list[TaskRetried] = []

        async def _on_retried(event: TaskRetried) -> None:
            received.append(event)

        event_bus.subscribe(TaskRetried, _on_retried)

        original = _make_row(
            task_name="orders.ship",
            status=TaskStatus.FAILED,
            args=[42],
            kwargs={"priority": "high"},
            queue="orders",
        )
        db_session.add(original)
        await db_session.flush()
        await db_session.refresh(original)

        detail = await service.retry(original.id)

        mock_celery.send_task.assert_called_once_with(
            "orders.ship",
            args=[42],
            kwargs={"priority": "high"},
            queue="orders",
        )
        assert detail.retried_from_id == original.id
        assert detail.status == TaskStatus.PENDING
        assert detail.celery_task_id == "new-celery-id-123"
        assert len(received) == 1
        assert received[0].original_id == original.id
        assert received[0].new_id == detail.id

    async def test_retry_stuck_task_is_allowed(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        row = _make_row(status=TaskStatus.STUCK)
        db_session.add(row)
        await db_session.flush()
        await db_session.refresh(row)

        detail = await service.retry(row.id)
        assert detail.retried_from_id == row.id

    async def test_retry_rejects_non_retryable_status(
        self, db_session: AsyncSession, service: BackgroundTaskService
    ):
        row = _make_row(status=TaskStatus.SUCCESS)
        db_session.add(row)
        await db_session.flush()
        await db_session.refresh(row)

        with pytest.raises(HTTPException) as exc:
            await service.retry(row.id)
        assert exc.value.status_code == 409

    async def test_retry_missing_row_404s(self, service: BackgroundTaskService):
        with pytest.raises(HTTPException) as exc:
            await service.retry(uuid.uuid4())
        assert exc.value.status_code == 404
