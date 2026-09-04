"""Detail view props.

The subline reads "attempt {n} of {max}". ``retries`` ships on the row already;
``max_retries`` is module configuration and has to be handed to the page, or
the sentence has no denominator and the operator cannot tell a first failure
from the last one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.constants import TaskStatus
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


class TestMaxRetries:
    async def test_detail_carries_the_configured_ceiling(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        row = await _seed(app)

        props = await _detail(authenticated_client, row.id)

        assert props["max_retries"] == app.state.background_tasks.settings.max_retries

    async def test_follows_the_module_setting_rather_than_a_constant(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        row = await _seed(app)
        app.state.background_tasks.settings.max_retries = 7

        props = await _detail(authenticated_client, row.id)

        assert props["max_retries"] == 7

    async def test_execution_still_carries_the_attempt_count(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        row = await _seed(app, retries=1)

        props = await _detail(authenticated_client, row.id)

        assert props["execution"]["retries"] == 1
