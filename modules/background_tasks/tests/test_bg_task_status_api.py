"""Owner-scoped task status endpoint (#536)."""

from __future__ import annotations

import httpx
import pytest
from background_tasks.constants import TaskStatus
from simple_module_core.tenancy import TenantRole

URL = "/api/background_tasks/tasks/{}/status"
SECRETS = {"args", "kwargs", "result", "traceback", "owner_user_id", "tenant_id"}


def _seed(seed_execution, tenant, owner, **fields):
    return seed_execution(
        status=TaskStatus.RUNNING,
        tenant_id=tenant,
        owner_user_id=owner,
        progress_current=3,
        progress_total=10,
        progress_message="copying rows",
        progress_phase="copy",
        **fields,
    )


async def test_the_owner_sees_the_progress(seed_execution, tenant_client):
    async with tenant_client(TenantRole.MEMBER) as me:
        row = await _seed(seed_execution, me.tenant_id, me.user_id)

        resp = await me.client.get(URL.format(row.celery_task_id))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["progress_current"], body["progress_total"]) == (3, 10)
    assert (body["progress_message"], body["progress_phase"]) == ("copying rows", "copy")
    assert body["status"] == "running"
    assert SECRETS.isdisjoint(body)


async def test_another_member_of_the_tenant_gets_404(seed_execution, tenant_client):
    async with (
        tenant_client(TenantRole.MEMBER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as other,
    ):
        row = await _seed(seed_execution, owner.tenant_id, owner.user_id)

        resp = await other.client.get(URL.format(row.celery_task_id))

    assert resp.status_code == 404


async def test_the_owner_acting_in_another_tenant_gets_404(seed_execution, tenant_client):
    async with tenant_client() as home, tenant_client() as elsewhere:
        row = await _seed(seed_execution, home.tenant_id, elsewhere.user_id)

        resp = await elsewhere.client.get(URL.format(row.celery_task_id))

    assert resp.status_code == 404


async def test_a_task_nobody_owns_is_not_visible_to_members(seed_execution, tenant_client):
    async with tenant_client(TenantRole.MEMBER) as me:
        row = await _seed(seed_execution, me.tenant_id, None)

        assert (await me.client.get(URL.format(row.celery_task_id))).status_code == 404


async def test_an_unknown_task_is_404(tenant_client):
    async with tenant_client() as me:
        assert (await me.client.get(URL.format("nope"))).status_code == 404


async def test_a_task_viewer_sees_any_task(seed_execution, authenticated_client: httpx.AsyncClient):
    row = await _seed(seed_execution, "acme", "someone-else")

    resp = await authenticated_client.get(URL.format(row.celery_task_id))

    assert resp.status_code == 200
    assert resp.json()["progress_current"] == 3


async def test_the_error_is_a_type_name_never_a_traceback(
    seed_execution, authenticated_client: httpx.AsyncClient
):
    row = await seed_execution(
        status=TaskStatus.FAILED,
        owner_user_id="u",
        exception_type="ValueError",
        traceback="Traceback ... secret-token",
        result={"password": "x"},
    )

    resp = await authenticated_client.get(URL.format(row.celery_task_id))

    assert resp.json()["exception_type"] == "ValueError"
    assert "secret-token" not in resp.text
    assert "password" not in resp.text


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("Boom: leaked message", id="message"),
        # The column is varchar(255), the same cap as the pattern, so a stored
        # value is never too long; a trailing newline is what can leak.
        pytest.param("ValueError\nsecret=hunter2", id="multiline"),
        pytest.param("ValueError\n", id="trailing-newline"),
    ],
)
async def test_a_malformed_exception_type_is_dropped(
    bad, seed_execution, authenticated_client: httpx.AsyncClient
):
    row = await seed_execution(status=TaskStatus.FAILED, exception_type=bad)

    resp = await authenticated_client.get(URL.format(row.celery_task_id))

    assert resp.json()["exception_type"] is None


async def test_anonymous_callers_are_refused(client: httpx.AsyncClient):
    assert (await client.get(URL.format("abc"))).status_code in {302, 401}
