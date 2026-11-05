"""Newest-first ordering is one clause, shared by the list and the status lookup."""

from __future__ import annotations

from datetime import UTC, datetime

from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.service import BackgroundTaskService
from simple_module_core.tenancy import TenantRole

URL = "/api/background_tasks/tasks/{}/status"


async def test_null_queued_at_does_not_win_the_status_lookup(app, seed_execution, tenant_client):
    async with tenant_client(TenantRole.MEMBER) as me:
        dated = await seed_execution(
            status=TaskStatus.RUNNING,
            tenant_id=me.tenant_id,
            owner_user_id=me.user_id,
            progress_message="dated",
            queued_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        )
        async with app.state.sm.db.session_factory() as session:
            session.add(
                TaskExecution(
                    celery_task_id=dated.celery_task_id,
                    task_name="demo.task",
                    status=TaskStatus.PENDING,
                    args=[],
                    kwargs={},
                    tenant_id=me.tenant_id,
                    owner_user_id=me.user_id,
                    progress_message="undated",
                    queued_at=None,
                )
            )
            await session.commit()

        resp = await me.client.get(URL.format(dated.celery_task_id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["progress_message"] == "dated"


async def test_has_any_probe(app, seed_execution):
    async with app.state.sm.db.session_factory() as session:
        service = BackgroundTaskService(session, None, None)
        assert await service.has_any() is False
    await seed_execution()
    async with app.state.sm.db.session_factory() as session:
        service = BackgroundTaskService(session, None, None)
        assert await service.has_any() is True
