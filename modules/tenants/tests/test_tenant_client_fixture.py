"""The shared ``tenant_client`` fixture and tenant-role vocabulary (#380)."""

from __future__ import annotations

import pytest
from simple_module_core.tenancy import TenantRole, tenant_role


@pytest.mark.parametrize("role", list(TenantRole))
async def test_fixture_creates_a_member_with_the_role(tenant_client, role):
    async with tenant_client(role) as (client, tenant_id, user_id):
        members = (await client.get("/api/tenants/current/members")).json()
        assert [(m["user_id"], m["role"]) for m in members] == [(user_id, role)]
        mine = (await client.get("/api/tenants/")).json()
        assert [t["id"] for t in mine] == [tenant_id]


async def test_second_member_joins_an_existing_tenant(tenant_client):
    async with (
        tenant_client() as owner,
        tenant_client("admin", tenant_id=owner.tenant_id) as admin,
    ):
        assert admin.tenant_id == owner.tenant_id
        resp = await admin.client.post("/api/tenants/current/invitations", json={"email": "n@x.io"})
        assert resp.status_code == 201


async def test_tenant_roles_reach_the_permission_registry(app):
    from tenants.constants import ROLE_PERMISSIONS, TENANT_ROLE_PREFIX, MembershipRole

    assert MembershipRole is TenantRole
    assert TENANT_ROLE_PREFIX == "tenant:"
    role_map = app.state.sm.permissions.role_map
    for role, perms in ROLE_PERMISSIONS.items():
        assert set(perms) <= set(role_map[tenant_role(role)])
