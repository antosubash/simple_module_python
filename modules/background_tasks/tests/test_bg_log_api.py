"""Retained-log endpoints and pages (GH #537)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from background_tasks.models import RetainedLog

BASE = "/api/background_tasks/admin"

pytestmark = pytest.mark.usefixtures("_stub_celery")


@pytest.fixture
def seed_logs(app):
    async def _seed(*rows: tuple[str, int, str | None, str | None]) -> None:
        """Each row is (message, level, task_id, tenant_id); newest last."""
        base = datetime.now(UTC) - timedelta(minutes=10)
        async with app.state.sm.db.session_factory() as session:
            for i, (message, level, task_id, tenant_id) in enumerate(rows):
                session.add(
                    RetainedLog(
                        ts=base + timedelta(seconds=i),
                        level=level,
                        logger="demo.worker",
                        message=message,
                        task_id=task_id,
                        tenant_id=tenant_id,
                    )
                )
            await session.commit()

    return _seed


async def test_task_lines_appear_on_the_execution_logs_endpoint(
    authenticated_client: httpx.AsyncClient, seed_execution, seed_logs
):
    execution = await seed_execution(celery_task_id="task-a")
    await seed_logs(
        ("step one", logging.INFO, "task-a", None),
        ("other task", logging.INFO, "task-b", None),
        ("step two", logging.ERROR, "task-a", None),
    )
    resp = await authenticated_client.get(f"{BASE}/executions/{execution.id}/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert [i["message"] for i in body["items"]] == ["step two", "step one"]
    assert body["items"][0]["level_name"] == "ERROR"
    assert body["total"] == 2


async def test_level_filter_is_a_minimum(
    authenticated_client: httpx.AsyncClient, seed_execution, seed_logs
):
    execution = await seed_execution(celery_task_id="task-a")
    await seed_logs(
        ("chatty", logging.DEBUG, "task-a", None),
        ("fine", logging.INFO, "task-a", None),
        ("careful", logging.WARNING, "task-a", None),
        ("bad", logging.ERROR, "task-a", None),
    )
    resp = await authenticated_client.get(
        f"{BASE}/executions/{execution.id}/logs", params={"level": "WARNING"}
    )
    assert [i["message"] for i in resp.json()["items"]] == ["bad", "careful"]


async def test_logs_are_paginated(
    authenticated_client: httpx.AsyncClient, seed_execution, seed_logs
):
    execution = await seed_execution(celery_task_id="task-a")
    await seed_logs(*[(f"line {i}", logging.INFO, "task-a", None) for i in range(5)])
    resp = await authenticated_client.get(
        f"{BASE}/executions/{execution.id}/logs", params={"per_page": 2, "page": 3}
    )
    body = resp.json()
    assert (body["total"], body["page"], len(body["items"])) == (5, 3, 1)


async def test_unknown_execution_is_404(authenticated_client: httpx.AsyncClient):
    resp = await authenticated_client.get(
        f"{BASE}/executions/00000000-0000-0000-0000-000000000000/logs"
    )
    assert resp.status_code == 404


async def test_search_filters_by_text_and_task(authenticated_client: httpx.AsyncClient, seed_logs):
    await seed_logs(
        ("disk 100% full", logging.ERROR, "task-a", None),
        ("disk fine", logging.INFO, "task-b", None),
        ("network up", logging.INFO, None, None),
    )
    by_text = await authenticated_client.get(f"{BASE}/logs", params={"q": "disk"})
    assert by_text.json()["total"] == 2
    percent = await authenticated_client.get(f"{BASE}/logs", params={"q": "100%"})
    assert [i["message"] for i in percent.json()["items"]] == ["disk 100% full"]
    by_task = await authenticated_client.get(f"{BASE}/logs", params={"task_id": "task-b"})
    assert [i["message"] for i in by_task.json()["items"]] == ["disk fine"]


async def test_logs_require_authentication(client: httpx.AsyncClient):
    resp = await client.get(f"{BASE}/logs", follow_redirects=False)
    assert resp.status_code in {302, 401, 403}


async def test_logs_page_renders_for_an_admin(authenticated_client: httpx.AsyncClient, seed_logs):
    await seed_logs(("hello", logging.INFO, None, None))
    resp = await authenticated_client.get(
        "/admin/background-tasks/logs", headers={"X-Inertia": "true"}
    )
    assert resp.status_code == 200
    page = resp.json()
    assert page["component"] == "BackgroundTasks/Logs"
    assert page["props"]["pagination"]["total"] == 1
