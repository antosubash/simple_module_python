"""A key set by upload is not cleared by a bare row delete (ship review).

A generic delete would drop the setting row but leave the stored file behind;
the key's ``clear_via`` route is what reaps it. The rule lives in
``SettingService`` and holds for every scope and every caller: the API routes,
the Inertia admin route and a direct service call. The one exception is a
TENANT row left by a deleted tenant, which a platform operator may clear.
"""

from __future__ import annotations

import pytest
from settings._managed_keys import ManagedKeyError
from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.registry import SettingDefinition
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService

KEY = "demo.logo"
UPLOAD = "/api/demo/tenant/logo"
INERTIA = {"X-Inertia": "true", "X-Inertia-Version": ""}


@pytest.fixture(autouse=True)
def definitions(app):
    app.state.settings.registry.add(
        SettingDefinition(key=KEY, tenant_overridable=True, clear_via=UPLOAD)
    )


async def _seed(app, scope: SettingScope, scope_id: str) -> int:
    async with app.state.sm.db.session_factory() as db:
        row = await SettingService(db).upsert_scoped(
            scope, scope_id, KEY, SettingUpsert(value="file-1")
        )
        await db.commit()
        return row.id


async def _exists(app, scope: SettingScope, scope_id: str) -> bool:
    async with app.state.sm.db.session_factory() as db:
        return await SettingService(db).get_scoped(scope, scope_id, KEY) is not None


async def test_self_service_delete_is_refused_and_row_kept(app, tenant_client):
    async with tenant_client() as t:
        await _seed(app, SettingScope.TENANT, t.tenant_id)
        resp = await t.client.delete(f"/api/settings/tenant/current/{KEY}")
        assert resp.status_code == 422
        assert UPLOAD in resp.json()["detail"]
        assert await _exists(app, SettingScope.TENANT, t.tenant_id)


async def test_platform_delete_is_refused_for_a_live_tenant(
    app, authenticated_client, tenant_client
):
    async with tenant_client() as t:
        await _seed(app, SettingScope.TENANT, t.tenant_id)
        resp = await authenticated_client.delete(f"/api/settings/tenant/{t.tenant_id}/{KEY}")
        assert resp.status_code == 422
        assert await _exists(app, SettingScope.TENANT, t.tenant_id)


async def test_api_delete_by_id_is_refused_for_tenant_and_system_rows(
    app, authenticated_client, tenant_client
):
    async with tenant_client() as t:
        tenant_row = await _seed(app, SettingScope.TENANT, t.tenant_id)
        system_row = await _seed(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        for row_id in (tenant_row, system_row):
            resp = await authenticated_client.delete(f"/api/settings/{row_id}")
            assert resp.status_code == 422
            assert UPLOAD in resp.json()["detail"]
        assert await _exists(app, SettingScope.TENANT, t.tenant_id)
        assert await _exists(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)


async def test_inertia_admin_delete_is_refused_for_tenant_and_system_rows(
    app, authenticated_client, tenant_client
):
    async with tenant_client() as t:
        tenant_row = await _seed(app, SettingScope.TENANT, t.tenant_id)
        system_row = await _seed(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        for row_id in (tenant_row, system_row):
            resp = await authenticated_client.delete(
                f"/admin/settings/{row_id}", headers=INERTIA, follow_redirects=False
            )
            assert resp.status_code in (302, 303)
        assert await _exists(app, SettingScope.TENANT, t.tenant_id)
        assert await _exists(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)


async def test_inertia_refusal_carries_a_translated_error(app, authenticated_client):
    row_id = await _seed(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
    resp = await authenticated_client.delete(
        f"/admin/settings/{row_id}",
        headers={**INERTIA, "Referer": "http://test/admin/settings/store"},
    )
    # The error rides the session to the next page render, as for any form.
    page = await authenticated_client.get("/admin/settings/store")
    assert "is managed elsewhere" in page.text, resp.status_code


async def test_direct_service_call_is_refused(app, tenant_client):
    async with tenant_client() as t:
        tenant_row = await _seed(app, SettingScope.TENANT, t.tenant_id)
        await _seed(app, SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        registry = app.state.settings.registry
        async with app.state.sm.db.session_factory() as db:
            service = SettingService(db, registry=registry)
            with pytest.raises(ManagedKeyError) as err:
                await service.delete(tenant_row)
            assert err.value.clear_via == UPLOAD
            with pytest.raises(ManagedKeyError):
                await service.delete_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, KEY)
            # The owner, having a reap to run, may stand the guard down.
            assert await service.delete_scoped(
                SettingScope.SYSTEM, SYSTEM_SCOPE_ID, KEY, as_owner=True
            )


async def test_platform_may_clear_a_row_left_by_a_deleted_tenant(app, authenticated_client):
    row_id = await _seed(app, SettingScope.TENANT, "gone-tenant")
    resp = await authenticated_client.delete(f"/api/settings/tenant/gone-tenant/{KEY}")
    assert resp.status_code == 204
    assert not await _exists(app, SettingScope.TENANT, "gone-tenant")
    row_id = await _seed(app, SettingScope.TENANT, "gone-tenant")
    resp = await authenticated_client.delete(f"/api/settings/{row_id}")
    assert resp.status_code == 204


async def test_plain_keys_still_delete(app, authenticated_client, tenant_client):
    app.state.settings.registry.add(SettingDefinition(key="demo.plain", tenant_overridable=True))
    async with tenant_client() as t:
        await t.client.put("/api/settings/tenant/current/demo.plain", json={"value": "x"})
        assert (await t.client.delete("/api/settings/tenant/current/demo.plain")).status_code == 204
    async with app.state.sm.db.session_factory() as db:
        service = SettingService(db)
        first = await service.upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "demo.plain", SettingUpsert(value="y")
        )
        second = await service.upsert_scoped(
            SettingScope.USER, "u1", "demo.plain", SettingUpsert(value="z")
        )
        await db.commit()
    assert (await authenticated_client.delete(f"/api/settings/{first.id}")).status_code == 204
    resp = await authenticated_client.delete(
        f"/admin/settings/{second.id}", headers=INERTIA, follow_redirects=False
    )
    assert resp.status_code in (302, 303)
    async with app.state.sm.db.session_factory() as db:
        assert await SettingService(db).get_by_id(second.id) is None
