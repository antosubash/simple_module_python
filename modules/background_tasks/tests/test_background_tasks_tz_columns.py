"""#413: every TaskExecution timestamp is timezone-aware, so aware cutoffs bind on Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.service import BackgroundTaskService
from simple_module_core.events import EventBus
from simple_module_db import RequestSession
from users.models.refresh_token import RefreshToken

_AWARE = {
    TaskExecution: (
        "queued_at",
        "started_at",
        "finished_at",
        "heartbeat_at",
        "created_at",
        "updated_at",
    ),
    RefreshToken: ("created_at", "expires_at", "revoked_at"),
}


@pytest.mark.parametrize(("model", "column"), [(m, c) for m, cols in _AWARE.items() for c in cols])
def test_timestamp_columns_are_timezone_aware(model, column):
    assert model.__table__.c[column].type.timezone is True


async def test_success_count_since_binds_an_aware_cutoff(db_session: RequestSession):
    """Raised asyncpg DataError on Postgres before #406; runs there under make test-py-pg."""
    service = BackgroundTaskService(db=db_session, celery=MagicMock(), event_bus=EventBus())
    assert await service.success_count_since() == 0

    now = datetime.now(UTC)
    db_session.add(
        TaskExecution(
            celery_task_id=str(uuid.uuid4()),
            task_name="demo.task",
            status=TaskStatus.SUCCESS,
            queue="default",
            args=[],
            kwargs={},
            queued_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    assert await service.success_count_since(hours=1) == 1
    assert await service.success_count_since(hours=1, queue="other") == 0
