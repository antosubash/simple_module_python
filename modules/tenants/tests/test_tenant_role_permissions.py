"""Tenant roles never alias platform roles in the permission chain (#377).

A tenant membership role reaches the principal as ``tenant:<role>``; the
registry maps that onto tenant permissions only, and the platform ``admin``
wildcard stays a different principal entirely.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from simple_module_core.permissions import ADMIN_ROLE, WILDCARD
from simple_module_core.tenancy import TENANT_ROLE_PREFIX, TenantRole, is_tenant_role, tenant_role
from simple_module_hosting.permissions import resolved_permissions_for
from tenants.constants import ROLE_PERMISSIONS
from users.models import Role


@pytest.fixture
def probe(app):
    """``GET /__probe`` -> the roles and resolved permissions the request holds."""

    @app.get("/__probe")
    async def _probe(request: Request):
        user = request.state.user
        return {
            "roles": list(user.roles),
            "permissions": sorted(resolved_permissions_for(request)),
        }

    return "/__probe"


class TestReservedRoleNames:
    @pytest.mark.parametrize("name", ["tenant:admin", "tenant:owner", "tenant:custom", "TENANT:x"])
    def test_constructing_a_role_in_the_namespace_is_refused(self, name):
        with pytest.raises(ValueError, match="reserved for tenant roles"):
            Role(name=name)

    def test_renaming_a_role_into_the_namespace_is_refused(self):
        role = Role(name="editor")
        with pytest.raises(ValueError, match="reserved for tenant roles"):
            role.name = f"{TENANT_ROLE_PREFIX}admin"
        assert role.name == "editor"

    def test_lookalikes_outside_the_namespace_are_fine(self):
        for name in ("admin", "tenant", "tenants:admin", "my-tenant:admin"):
            assert Role(name=name).name == name


class TestTenantAdminIsNotPlatformAdmin:
    def test_tenant_roles_hold_no_wildcard_and_are_distinct_from_admin(self, app):
        role_map = app.state.sm.permissions.role_map
        assert WILDCARD in role_map[ADMIN_ROLE]
        for role in TenantRole:
            key = tenant_role(role)
            assert key != ADMIN_ROLE and is_tenant_role(key)
            assert WILDCARD not in role_map[key]
            assert set(role_map[key]) == set(ROLE_PERMISSIONS[role])
            assert not any(".platform." in p for p in role_map[key])

    async def test_tenant_admin_is_refused_platform_routes(self, tenant_client):
        async with tenant_client("admin") as admin:
            assert (await admin.client.get("/api/tenants/admin/")).status_code == 403
            assert (await admin.client.get("/api/tenants/current/members")).status_code == 200

    async def test_platform_admin_still_holds_everything(self, authenticated_client):
        assert (await authenticated_client.get("/api/tenants/admin/")).status_code == 200


class TestSyncAdminAllPermissions:
    async def test_never_touches_tenant_roles(self, app, db_session):
        from permissions.models import RolePermission
        from permissions.service import PermissionService
        from sqlalchemy import select
        from users.constants import ADMIN_ROLE_NAME

        registry = app.state.sm.permissions
        before = {r: sorted(p) for r, p in registry.role_map.items() if is_tenant_role(r)}
        assert before  # the tenants module mapped them

        await PermissionService(db_session, registry).sync_admin_all_permissions()
        await db_session.flush()

        rows = (await db_session.execute(select(RolePermission.role_name).distinct())).scalars()
        assert set(rows) == {ADMIN_ROLE_NAME}
        after = {r: sorted(p) for r, p in registry.role_map.items() if is_tenant_role(r)}
        assert after == before


class TestEffectivePermissions:
    @pytest.mark.parametrize("role", list(TenantRole))
    async def test_member_gets_registry_mapping_and_no_platform_extras(
        self, tenant_client, probe, app, role
    ):
        role_map = app.state.sm.permissions.role_map
        async with tenant_client(role) as m:
            body = (await m.client.get(probe)).json()
        assert tenant_role(role) in body["roles"]
        assert ADMIN_ROLE not in body["roles"]
        platform = [r for r in body["roles"] if not is_tenant_role(r)]
        expected = set(role_map[tenant_role(role)])
        for r in platform:  # the fixture user's ordinary ``user`` role, if mapped
            expected |= set(role_map.get(r, []))
        assert set(body["permissions"]) == expected
        assert WILDCARD not in body["permissions"]

    async def test_only_the_active_tenants_role_applies(self, tenant_client, probe):
        async with tenant_client("owner") as a, tenant_client("member") as b:
            a_roles = (await a.client.get(probe)).json()["roles"]
            b_roles = (await b.client.get(probe)).json()["roles"]
        assert [r for r in a_roles if is_tenant_role(r)] == ["tenant:owner"]
        assert [r for r in b_roles if is_tenant_role(r)] == ["tenant:member"]
