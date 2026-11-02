"""``?page=0`` / ``?page=-1`` on the admin index view must clamp, not 422.

``BackgroundTaskService.list()`` already clamps ``page`` to at least 1, but a
strict ``ge=1`` on the endpoint's ``Query`` used to reject the request before
that clamp ever ran — so a hand-edited or bookmarked ``?page=0`` rendered the
app's raw "invalid parameters" error page instead of the listing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution

VIEW_BASE = "/admin/background-tasks/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")


async def _seed(app) -> TaskExecution:
    row = TaskExecution(
        celery_task_id=str(uuid.uuid4()),
        task_name="demo.a",
        status=TaskStatus.FAILED,
        queue="default",
        args=[],
        kwargs={},
        queued_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


class TestPageBelowOneClamps:
    @pytest.mark.parametrize("page", [0, -1])
    async def test_clamps_to_page_one_and_renders_rows(
        self,
        page: int,
        app,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        await _seed(app)

        resp = await authenticated_client.get(
            VIEW_BASE, params={"page": page}, headers=INERTIA_HEADERS
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "BackgroundTasks/Index"
        assert body["props"]["pagination"]["page"] == 1
        assert [i["task_name"] for i in body["props"]["executions"]] == ["demo.a"]
