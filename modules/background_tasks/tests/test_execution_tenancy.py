"""TaskExecution carries the tenant it was published for (#371).

The table is not tenant-scoped (beat publishes have no tenant); the admin
screens are platform-wide and filter on the column. Retries re-publish as the
original row's tenant, not the operator's.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from background_tasks import sync_db
from background_tasks.constants import PLATFORM_TENANT_FILTER, TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.retry_service import RetryCoordinator
from background_tasks.signals import on_task_publish
from background_tasks.tenant_context import TENANT_HEADER
from simple_module_core.tenancy import TenantRole
from simple_module_db import current_tenant_id, tenant_context
from sqlalchemy import select

ADMIN = "/api/background_tasks/admin"


def _publish(headers: dict | None = None) -> str:
    task_id = str(uuid.uuid4())
    on_task_publish(
        sender="demo.echo",
        headers={"id": task_id, "task": "demo.echo", **(headers or {})},
        body=([], {}, {}),
    )
    return task_id


def _tenant_of(task_id: str) -> str | None:
    with sync_db.get_sync_session_factory()() as session:
        return session.execute(
            select(TaskExecution.tenant_id).where(TaskExecution.celery_task_id == task_id)
        ).scalar_one()


class TestPublishStamp:
    def test_publish_under_a_tenant_stamps_it(self, sync_sqlite: Path):
        with tenant_context("acme"):
            task_id = _publish()
        assert _tenant_of(task_id) == "acme"

    def test_beat_or_platform_publish_stays_null(self, sync_sqlite: Path):
        assert _tenant_of(_publish()) is None

    def test_platform_code_may_name_the_tenant_in_the_header(self, sync_sqlite: Path):
        assert _tenant_of(_publish({TENANT_HEADER: "globex"})) == "globex"

    def test_a_later_signal_does_not_blank_the_tenant(self, sync_sqlite: Path):
        with tenant_context("acme"):
            task_id = _publish()
        # Republished with no tenant (e.g. the retry's send under no context).
        on_task_publish(
            sender="demo.echo", headers={"id": task_id, "task": "demo.echo"}, body=([], {}, {})
        )
        assert _tenant_of(task_id) == "acme"


def _coordinator() -> tuple[RetryCoordinator, list[str | None]]:
    seen: list[str | None] = []
    celery = MagicMock(name="Celery")

    def send_task(*_a, **_k):
        seen.append(current_tenant_id.get())
        return MagicMock(id="mocked-id")

    celery.send_task.side_effect = send_task
    return RetryCoordinator(MagicMock(), celery, MagicMock()), seen


def _row(tenant_id: str | None) -> TaskExecution:
    return TaskExecution(task_name="demo.echo", queue="default", tenant_id=tenant_id)


class TestRetryPublish:
    def test_publishes_as_the_row_tenant_not_the_operators(self):
        coordinator, seen = _coordinator()
        with tenant_context("operators-org"):
            coordinator._publish(_row("acme"))
        assert seen == ["acme"]

    def test_a_platform_row_is_published_with_no_tenant(self):
        coordinator, seen = _coordinator()
        with tenant_context("operators-org"):
            coordinator._publish(_row(None))
        assert seen == [None]

    def test_the_new_attempt_copies_the_tenant(self):
        coordinator, _ = _coordinator()
        assert coordinator._new_attempt(_row("acme"), "new-id").tenant_id == "acme"
        assert coordinator._new_attempt(_row(None), "new-id").tenant_id is None


@pytest.mark.usefixtures("_stub_celery")
class TestRetryEndpoints:
    @pytest.fixture
    def seen(self, app) -> list[str | None]:
        seen: list[str | None] = []

        def send_task(*_a, **_k):
            seen.append(current_tenant_id.get())
            return MagicMock(id=str(uuid.uuid4()))

        app.state.background_tasks.celery.send_task.side_effect = send_task
        return seen

    async def test_single_retry_runs_as_the_original_tenant(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient, seen
    ):
        original = await seed_execution(status=TaskStatus.FAILED, tenant_id="acme")

        resp = await authenticated_client.post(f"{ADMIN}/executions/{original.id}/retry")

        assert resp.status_code == 200, resp.text
        assert resp.json()["tenant_id"] == "acme"
        assert seen == ["acme"]
        assert sorted(r.tenant_id for r in await execution_rows()) == ["acme", "acme"]

    async def test_bulk_retry_runs_each_row_as_its_own_tenant(
        self, seed_execution, execution_rows, authenticated_client: httpx.AsyncClient, seen
    ):
        await seed_execution(status=TaskStatus.FAILED, tenant_id="acme")
        await seed_execution(status=TaskStatus.FAILED, tenant_id="globex")
        await seed_execution(status=TaskStatus.FAILED)

        resp = await authenticated_client.post(f"{ADMIN}/executions/retry-failed")

        assert resp.json() == {"queued": 3, "remaining": 0}
        assert sorted(seen, key=str) == [None, "acme", "globex"]
        children = [r for r in await execution_rows() if r.retried_from_id]
        assert sorted((r.tenant_id or "") for r in children) == ["", "acme", "globex"]

    async def test_bulk_retry_can_be_narrowed_to_a_tenant(
        self, seed_execution, authenticated_client: httpx.AsyncClient, seen
    ):
        await seed_execution(status=TaskStatus.FAILED, tenant_id="acme")
        await seed_execution(status=TaskStatus.FAILED, tenant_id="globex")

        resp = await authenticated_client.post(
            f"{ADMIN}/executions/retry-failed", params={"tenant_id": "acme"}
        )

        assert resp.json() == {"queued": 1, "remaining": 0}
        assert seen == ["acme"]


class TestTenantFilter:
    async def test_list_filters_by_tenant_and_platform(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ):
        await seed_execution(task_name="a", tenant_id="acme")
        await seed_execution(task_name="g", tenant_id="globex")
        await seed_execution(task_name="p")

        async def names(**params: str) -> set[str]:
            resp = await authenticated_client.get(f"{ADMIN}/executions", params=params)
            return {i["task_name"] for i in resp.json()["items"]}

        assert await names() == {"a", "g", "p"}
        assert await names(tenant_id="acme") == {"a"}
        assert await names(tenant_id=PLATFORM_TENANT_FILTER) == {"p"}

    async def test_index_view_exposes_tenants_and_echoes_the_filter(
        self, seed_execution, authenticated_client: httpx.AsyncClient
    ):
        await seed_execution(task_name="a", tenant_id="acme")
        await seed_execution(task_name="g", tenant_id="globex")

        resp = await authenticated_client.get(
            "/admin/background-tasks/",
            params={"tenant": "acme"},
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )

        props = resp.json()["props"]
        assert props["tenant_ids"] == ["acme", "globex"]
        assert props["filters"]["tenant"] == "acme"
        assert [e["task_name"] for e in props["executions"]] == ["a"]
        assert props["pagination"]["total"] == 1


@pytest.mark.parametrize("role", list(TenantRole))
async def test_tenant_members_cannot_read_executions(tenant_client, role):
    async with tenant_client(role) as m:
        assert (await m.client.get(f"{ADMIN}/executions")).status_code == 403
