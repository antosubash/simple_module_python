"""HTTP principal loading retains the existing caches and authentication semantics."""

import asyncio
import uuid

import pytest
from fastapi import Depends
from permissions.grants import source as grants
from permissions.models import RolePermission, UserPermission
from simple_module_core.resources import ResourcePrincipal
from simple_module_hosting import middleware
from simple_module_hosting.resource_deps import resource_principal
from sqlalchemy import delete, event
from tenants.models import Membership, Tenant
from tenants.resolution.resolver import forget


@pytest.mark.parametrize("cold", [False, True])
async def test_request_permission_queries_use_cache_and_singleflight(
    app, tenant_client, monkeypatch, cold
):
    @app.get("/principal-cache")
    async def probe(who: ResourcePrincipal = Depends(resource_principal)):
        return sorted(who.permissions)

    queries = []
    resolution_queries = []
    resolve = middleware.resolve_request_permissions

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        queries.append(statement)

    async def counted(request, registry):
        before = len(queries)
        result = await resolve(request, registry)
        resolution_queries.append(len(queries) - before)
        return result

    monkeypatch.setattr(middleware, "resolve_request_permissions", counted)
    async with tenant_client("member") as (client, _, user_id):
        async with app.state.sm.db.session_factory() as db:
            db.add(RolePermission(role_name="user", permission_key="test.cached.role"))
            db.add(UserPermission(user_id=uuid.UUID(user_id), permission_key="test.cached.direct"))
            await db.commit()
        await app.state.sm.invalidation.publish("permissions.role_grants", key="user")
        assert (await client.get("/principal-cache")).status_code == 200
        event.listen(app.state.sm.db.engine.sync_engine, "before_cursor_execute", record)
        try:
            if cold:
                grants.clear_grants_cache()
            responses = await asyncio.gather(*[client.get("/principal-cache") for _ in range(20)])
        finally:
            event.remove(app.state.sm.db.engine.sync_engine, "before_cursor_execute", record)
        assert all(response.status_code == 200 for response in responses)
        assert all(
            {"test.cached.role", "test.cached.direct"} <= set(response.json())
            for response in responses
        )
    if cold:
        # Twenty real HTTP requests share a single cold direct-grant read.
        reads = [sql for sql in queries if "permissions_user_permission" in sql.lower()]
        assert len(reads) == 1
    else:
        # origin/main adds zero queries here on a warm non-admin request.
        assert resolution_queries[-20:] == [0] * 20
        assert not any("tenants_membership" in sql.lower() for sql in queries)
        assert not any("permissions_role_permission" in sql.lower() for sql in queries)


async def test_removed_membership_keeps_authentication_and_can_switch(app, tenant_client):
    async with tenant_client("owner") as (client, tenant_a, user_id):
        async with app.state.sm.db.session_factory() as db:
            tenant_b = Tenant(name="Still a member", slug="still-a-member")
            db.add(tenant_b)
            await db.flush()
            db.add(Membership(tenant_id=tenant_b.id, user_id=user_id, role="owner"))
            await db.commit()
        forget(user_id)
        assert (await client.get("/api/tenants/current/members")).status_code == 200
        async with app.state.sm.db.session_factory() as db:
            await db.execute(delete(Membership).where(Membership.tenant_id == tenant_a))
            await db.commit()
        # A warm selection of removed A must not invalidate the account or block B.
        assert (await client.get("/api/tenants/")).status_code == 200
        assert (await client.post(f"/api/tenants/{tenant_b.id}/switch")).status_code == 204
        forget(user_id)
        response = await client.get("/api/tenants/current/members")
        assert response.status_code == 200
        assert response.json()["items"][0]["user_id"] == user_id
        # Once membership invalidation arrives, an explicit request for A is forbidden.
        response = await client.get(
            "/api/tenants/current/members", headers={"X-Tenant-ID": tenant_a}
        )
        assert response.status_code == 403
        assert (await client.get("/api/tenants/")).status_code == 200
