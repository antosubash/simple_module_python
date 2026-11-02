"""Feature flags under multi-tenancy (#375).

Request-time checks (``require_flag`` / ``is_flag_enabled``) already resolve
``request.state.tenant_id``; boot hydration is deliberately cross-tenant; the
admin tenant-override endpoints refuse a tenant that does not exist.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from feature_flags.constants import PERM_FEATURE_FLAGS_MANAGE, PERM_FEATURE_FLAGS_VIEW
from feature_flags.service import FeatureFlagService
from simple_module_core.feature_flags import FeatureFlagRegistry, require_flag
from simple_module_core.tenancy import TenantRole, tenant_role

FLAG = "file_storage.public_uploads"  # default off
SYSTEM = f"/api/feature_flags/{FLAG}"


def tenant_url(tenant_id: str) -> str:
    return f"/api/feature_flags/tenant/{tenant_id}/{FLAG}"


@pytest.fixture
def gated(app):
    """``GET /__gated`` — 200 when ``FLAG`` is on for the caller's tenant, else 404."""

    @app.get("/__gated", dependencies=[Depends(require_flag(FLAG))])
    async def _gated() -> dict:
        return {"ok": True}

    return "/__gated"


async def _put(client, url, enabled):
    resp = await client.put(url, json={"enabled": enabled})
    assert resp.status_code == 200, resp.text


class TestRequireFlagResolvesTheRequestTenant:
    async def test_two_tenants_with_different_overrides(
        self, authenticated_client, tenant_client, gated
    ):
        async with tenant_client() as a, tenant_client() as b:
            await _put(authenticated_client, tenant_url(a.tenant_id), True)
            await _put(authenticated_client, tenant_url(b.tenant_id), False)
            assert (await a.client.get(gated)).status_code == 200
            assert (await b.client.get(gated)).status_code == 404

    async def test_tenant_override_beats_system_in_both_directions(
        self, authenticated_client, tenant_client, gated
    ):
        async with tenant_client() as a, tenant_client() as b, tenant_client() as c:
            await _put(authenticated_client, SYSTEM, True)
            await _put(authenticated_client, tenant_url(a.tenant_id), False)
            # system on: A overridden off, B inherits on
            assert (await a.client.get(gated)).status_code == 404
            assert (await b.client.get(gated)).status_code == 200
            await _put(authenticated_client, SYSTEM, False)
            await _put(authenticated_client, tenant_url(c.tenant_id), True)
            # system off: C overridden on, B inherits off, A keeps its own off
            assert (await c.client.get(gated)).status_code == 200
            assert (await b.client.get(gated)).status_code == 404

    async def test_default_applies_when_nothing_is_overridden(self, tenant_client, gated):
        async with tenant_client() as a:
            assert (await a.client.get(gated)).status_code == 404

    async def test_clearing_a_tenant_override_falls_back_to_system(
        self, authenticated_client, tenant_client, gated
    ):
        async with tenant_client() as a:
            await _put(authenticated_client, SYSTEM, True)
            await _put(authenticated_client, tenant_url(a.tenant_id), False)
            assert (await a.client.get(gated)).status_code == 404
            cleared = await authenticated_client.delete(tenant_url(a.tenant_id))
            assert cleared.status_code == 204
            assert (await a.client.get(gated)).status_code == 200


class TestBootHydration:
    async def test_loads_every_tenants_overrides_with_no_tenant_bound(self, app, tenant_client):
        assert app.state.sm.db.tenant_strict  # strict: an unscoped tenant read would raise
        async with tenant_client() as a, tenant_client() as b:
            async with app.state.sm.db.session_factory() as db:
                service = FeatureFlagService(db)
                await service.set_override(FLAG, True, scope="tenant", scope_id=a.tenant_id)
                await service.set_override(FLAG, False, scope="tenant", scope_id=b.tenant_id)
                await db.commit()

            fresh = FeatureFlagRegistry()
            async with app.state.sm.db.session_factory() as db:
                loaded = await FeatureFlagService(db).hydrate_registry(fresh)

        assert loaded >= 2
        assert fresh.tenant_override(FLAG, a.tenant_id) is True
        assert fresh.tenant_override(FLAG, b.tenant_id) is False


class TestTenantRolesNeverManageFlags:
    @pytest.mark.parametrize("role", list(TenantRole))
    def test_no_tenant_role_holds_flag_permissions(self, app, role):
        mapped = set(app.state.sm.permissions.role_map[tenant_role(role)])
        assert PERM_FEATURE_FLAGS_MANAGE not in mapped
        assert PERM_FEATURE_FLAGS_VIEW not in mapped

    @pytest.mark.parametrize("role", list(TenantRole))
    async def test_tenant_member_cannot_reach_the_admin_endpoints(self, tenant_client, role):
        async with tenant_client(role) as m:
            own = tenant_url(m.tenant_id)
            assert (await m.client.put(own, json={"enabled": True})).status_code == 403
            assert (await m.client.delete(own)).status_code == 403
            listing = await m.client.get(f"/api/feature_flags/tenant/{m.tenant_id}")
            assert listing.status_code == 403


class TestUnknownTenantIsRejected:
    async def test_set_override_for_an_unknown_tenant_404s_and_persists_nothing(
        self, authenticated_client, app
    ):
        resp = await authenticated_client.put(tenant_url("no-such-tenant"), json={"enabled": True})
        assert resp.status_code == 404
        assert app.state.sm.feature_flags.tenant_override(FLAG, "no-such-tenant") is None
        async with app.state.sm.db.session_factory() as db:
            known = await FeatureFlagService(db).list_tenants_with_overrides()
        assert "no-such-tenant" not in known

    async def test_listing_an_unknown_tenant_404s(self, authenticated_client):
        resp = await authenticated_client.get("/api/feature_flags/tenant/no-such-tenant")
        assert resp.status_code == 404

    async def test_known_tenant_is_accepted(self, authenticated_client, tenant_client):
        async with tenant_client() as a:
            await _put(authenticated_client, tenant_url(a.tenant_id), True)
            listing = await authenticated_client.get(f"/api/feature_flags/tenant/{a.tenant_id}")
            assert listing.status_code == 200

    async def test_browse_view_rejects_an_unknown_tenant(self, authenticated_client):
        resp = await authenticated_client.get("/admin/feature-flags/?tenant_id=nope")
        assert resp.status_code == 404
        assert (await authenticated_client.get("/admin/feature-flags/")).status_code == 200

    async def test_an_orphaned_override_can_still_be_cleared(self, authenticated_client, app):
        async with app.state.sm.db.session_factory() as db:
            await FeatureFlagService(db).set_override(
                FLAG, True, registry=app.state.sm.feature_flags, scope="tenant", scope_id="gone"
            )
            await db.commit()
        resp = await authenticated_client.delete(tenant_url("gone"))
        assert resp.status_code == 204


async def test_without_a_tenant_directory_any_id_is_accepted(authenticated_client, app):
    """No ``tenants`` module installed means nobody can say a tenant is unknown."""
    saved = app.state.tenant_exists
    del app.state.tenant_exists
    try:
        resp = await authenticated_client.put(tenant_url("anything"), json={"enabled": True})
    finally:
        app.state.tenant_exists = saved
    assert resp.status_code == 200
