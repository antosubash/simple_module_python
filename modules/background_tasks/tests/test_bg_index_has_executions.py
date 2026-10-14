"""The index view's ``has_executions`` prop (GH #469).

``pagination.total`` is the *filtered* count, so a search on an install with no
executions at all looked identical to a search hiding existing rows, and the
empty state claimed rows "exist outside the current search". The prop carries
the unfiltered answer.
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


async def _props(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_BASE, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    return resp.json()["props"]


async def _seed(app) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.add(
            TaskExecution(
                celery_task_id=str(uuid.uuid4()),
                task_name="demo.a",
                status=TaskStatus.FAILED,
                queue="default",
                args=[],
                kwargs={},
                queued_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            )
        )
        await session.commit()


async def test_empty_install_reports_none_even_when_searching(
    authenticated_client: httpx.AsyncClient,
) -> None:
    assert (await _props(authenticated_client))["has_executions"] is False
    assert (await _props(authenticated_client, q="anything"))["has_executions"] is False


async def test_filters_hiding_existing_rows_still_report_some(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    await _seed(app)

    hidden = await _props(authenticated_client, q="no-such-task")
    assert hidden["pagination"]["total"] == 0
    assert hidden["has_executions"] is True
    assert (await _props(authenticated_client))["has_executions"] is True
