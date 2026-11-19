"""Detail props show actual retries without a module-wide retry ceiling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.core.constants import TaskStatus
from background_tasks.models import TaskExecution

VIEW_BASE = "/admin/background-tasks"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


async def _seed(app, *, retries: int = 0) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name="files.generate_thumbnail",
        status=TaskStatus.FAILED,
        queue="media",
        args=["a91f2c"],
        kwargs={"size": 512},
        retries=retries,
        queued_at=datetime.now(UTC),
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _detail(client: httpx.AsyncClient, execution_id) -> dict:
    resp = await client.get(f"{VIEW_BASE}/{execution_id}", headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["component"] == "BackgroundTasks/Detail"
    return body["props"]


async def test_execution_carries_the_actual_retry_count(app, authenticated_client):
    row = await _seed(app, retries=1)
    props = await _detail(authenticated_client, row.id)
    assert props["execution"]["retries"] == 1
    assert "max_retries" not in props
