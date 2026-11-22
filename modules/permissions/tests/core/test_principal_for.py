"""Request/headless principal parity over the real provider stores (#1005)."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import Depends
from permissions.core.service import PermissionService
from permissions.models import RolePermission, UserPermission
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.tenancy import TenantRole, tenant_role
from simple_module_hosting.resource_deps import resource_principal
from simple_module_test.tenant_client import create_user, session_client
from sqlalchemy import delete
from tenants.models import Membership, Tenant
from tenants.resolution.resolver import forget
from users.models import User


def test_public_api():
    from simple_module_db.principals import principal_for

    assert callable(principal_for)


@pytest.mark.parametrize(
    "case", ["role", "direct", "inactive", "disabled", "nonmember", "suspended"]
)
async def test_request_parity(app, tenant_client, case):
    from simple_module_db.principals import principal_for

    @app.get("/principal-parity")
    async def probe(who: ResourcePrincipal = Depends(resource_principal)):
        return {"user_id": who.user_id, "permissions": sorted(who.permissions)}

    registry = app.state.sm.permissions
    registry.map_role(tenant_role(TenantRole.MEMBER), ["test.member"])
    async with tenant_client("member") as (client, tenant_id, user_id):
        async with app.state.sm.db.session_factory() as db:
            db.add(RolePermission(role_name="user", permission_key="test.role"))
            if case == "direct":
                db.add(UserPermission(user_id=uuid.UUID(user_id), permission_key="test.direct"))
            elif case in {"inactive", "disabled"}:
                user = await db.get(User, uuid.UUID(user_id))
                if case == "inactive":
                    user.is_active = False
                else:
                    user.disabled_at = datetime.now(UTC)
            elif case == "nonmember":
                await db.execute(delete(Membership).where(Membership.user_id == user_id))
            elif case == "suspended":
                tenant = await db.get(Tenant, tenant_id)
                tenant.status = "suspended"
            await db.commit()
            await PermissionService(db, registry).load_all_into_registry()
        forget(user_id)
        async with app.state.sm.db.session_factory() as db:
            who = await principal_for(db, user_id, tenant_id)
        response = await client.get("/principal-parity", follow_redirects=False)
        if case in {"inactive", "disabled"}:
            assert who is None
            assert response.status_code in {302, 303, 401}
        elif case in {"nonmember", "suspended"}:
            assert who is None
            assert response.json()["user_id"] is None
        else:
            assert who is not None
            assert response.json() == {
                "user_id": who.user_id,
                "permissions": sorted(who.permissions),
            }
            assert {"test.member", "test.role"} <= who.permissions
            assert ("test.direct" in who.permissions) == (case == "direct")


@pytest.fixture
async def single_app(settings):
    from simple_module_test.fixtures import _build_app

    settings.multi_tenant = False
    settings.default_tenant = "single"
    async for app in _build_app(settings, seed_admin=True):
        yield app


async def test_single_tenant_needs_no_membership(single_app):
    from simple_module_db.principals import principal_for

    app = single_app
    user_id = await create_user(app, "single@example.com")

    async def request_grants(request, user):
        return ["test.single"] if user.tenant_id == "single" else []

    async def session_grants(db, user):
        return ["test.single"] if user.tenant_id == "single" else []

    app.state.sm.permissions.add_grant_source(request_grants, session_source=session_grants)

    @app.get("/principal-single")
    async def probe(who: ResourcePrincipal = Depends(resource_principal)):
        return {"user_id": who.user_id, "permissions": sorted(who.permissions)}

    async with app.state.sm.db.session_factory() as db:
        who = await principal_for(db, user_id, "single")
        assert who is not None
        assert "test.single" in who.permissions
        assert await principal_for(db, "missing", "single") is None
    async with session_client(app, {"user_id": user_id}) as client:
        response = await client.get("/principal-single")
    assert response.json() == {"user_id": who.user_id, "permissions": sorted(who.permissions)}
