"""Outbox admin is tenant-scoped for anyone but a platform admin (GH #459).

Outbox rows carry event payloads. Tenant members hold no background_tasks
permission by default (403); a tenant role *granted* it through the role editor
must still see and act on only its own tenant's rows, and another tenant's row
id must 404 rather than reveal that it exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from background_tasks.constants import PERM_MANAGE, PERM_VIEW, OutboxStatus
from background_tasks.models import OutboxMessage
from simple_module_core.tenancy import TenantRole, tenant_role

API = "/api/background_tasks/admin/outbox"
VIEW = "/admin/background-tasks/outbox"

pytestmark = pytest.mark.usefixtures("_stub_celery")


async def _seed(app, tenant_id: str | None, status: OutboxStatus = OutboxStatus.DEAD):
    now = datetime.now(UTC)
    row = OutboxMessage(
        event_key="x.Evt",
        payload={"secret": tenant_id},
        handler_name="h",
        tenant_id=tenant_id,
        status=status,
        next_attempt_at=now,
        created_at=now,
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()
    return row.id


@pytest.fixture
def tenant_admins_may_manage(app) -> None:
    """Grant the tenant admin role the outbox permissions, as the role editor could."""
    registry = app.state.sm.permissions
    role_map = dict(registry.role_map)
    role_map[tenant_role(TenantRole.ADMIN)] = [PERM_VIEW, PERM_MANAGE]
    registry._role_map_cache = role_map


async def test_tenant_member_without_grant_is_forbidden(tenant_client):
    async with tenant_client(TenantRole.ADMIN) as m:
        assert (await m.client.get(API)).status_code == 403


@pytest.mark.usefixtures("tenant_admins_may_manage")
class TestGrantedTenantAdmin:
    async def test_sees_only_its_own_tenant(self, app, tenant_client):
        async with tenant_client(TenantRole.ADMIN) as m:
            mine = await _seed(app, m.tenant_id)
            await _seed(app, "someone-else")
            await _seed(app, None)  # platform row

            body = (await m.client.get(API)).json()
            assert [i["id"] for i in body["items"]] == [str(mine)]
            assert body["counts"]["dead"] == 1

            page = await m.client.get(VIEW, headers={"X-Inertia": "true"})
            assert [r["id"] for r in page.json()["props"]["messages"]] == [str(mine)]

    async def test_cannot_retry_or_discard_another_tenants_row(self, app, tenant_client):
        async with tenant_client(TenantRole.ADMIN) as m:
            theirs = await _seed(app, "someone-else")
            platform = await _seed(app, None)
            for row_id in (theirs, platform):
                assert (await m.client.post(f"{API}/{row_id}/retry")).status_code == 404
                assert (await m.client.delete(f"{API}/{row_id}")).status_code == 404

        async with app.state.sm.db.session_factory() as session:
            for row_id in (theirs, platform):
                row = await session.get(OutboxMessage, row_id)
                assert row is not None and row.status == OutboxStatus.DEAD

    async def test_can_retry_and_discard_its_own(self, app, tenant_client):
        async with tenant_client(TenantRole.ADMIN) as m:
            retry_me = await _seed(app, m.tenant_id)
            drop_me = await _seed(app, m.tenant_id)
            assert (await m.client.post(f"{API}/{retry_me}/retry")).status_code == 200
            assert (await m.client.delete(f"{API}/{drop_me}")).status_code == 204


async def test_platform_admin_sees_every_tenant(app, authenticated_client):
    await _seed(app, "acme")
    await _seed(app, "globex")
    await _seed(app, None)
    assert (await authenticated_client.get(API)).json()["total"] == 3
