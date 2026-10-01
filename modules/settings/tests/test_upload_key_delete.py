"""A key set by upload is not cleared by a bare row delete (ship review).

A generic DELETE would drop the setting row but leave the stored file behind;
the key's ``upload_url`` route is what reaps it. A row left by a deleted tenant
may still be cleared by a platform operator.
"""

from __future__ import annotations

import pytest
from settings.contracts.registry import SettingDefinition
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService

KEY = "demo.logo"
UPLOAD = "/api/demo/tenant/logo"


@pytest.fixture(autouse=True)
def definitions(app):
    app.state.settings.registry.add(
        SettingDefinition(key=KEY, tenant_overridable=True, clear_via=UPLOAD)
    )


async def _seed(app, tenant_id: str) -> int:
    async with app.state.sm.db.session_factory() as db:
        row = await SettingService(db).upsert_scoped(
            SettingScope.TENANT, tenant_id, KEY, SettingUpsert(value="file-1")
        )
        await db.commit()
        return row.id


async def _exists(app, tenant_id: str) -> bool:
    async with app.state.sm.db.session_factory() as db:
        return await SettingService(db).get_scoped(SettingScope.TENANT, tenant_id, KEY) is not None


async def test_self_service_delete_is_refused_and_row_kept(app, tenant_client):
    async with tenant_client() as t:
        await _seed(app, t.tenant_id)
        resp = await t.client.delete(f"/api/settings/tenant/current/{KEY}")
        assert resp.status_code == 422
        assert UPLOAD in resp.json()["detail"]
        assert await _exists(app, t.tenant_id)


async def test_platform_delete_is_refused_for_a_live_tenant(
    app, authenticated_client, tenant_client
):
    async with tenant_client() as t:
        await _seed(app, t.tenant_id)
        resp = await authenticated_client.delete(f"/api/settings/tenant/{t.tenant_id}/{KEY}")
        assert resp.status_code == 422
        assert await _exists(app, t.tenant_id)


async def test_delete_by_id_is_refused_for_a_live_tenant(app, authenticated_client, tenant_client):
    async with tenant_client() as t:
        setting_id = await _seed(app, t.tenant_id)
        resp = await authenticated_client.delete(f"/api/settings/{setting_id}")
        assert resp.status_code == 422
        assert await _exists(app, t.tenant_id)


async def test_platform_may_clear_a_row_left_by_a_deleted_tenant(app, authenticated_client):
    await _seed(app, "gone-tenant")
    resp = await authenticated_client.delete(f"/api/settings/tenant/gone-tenant/{KEY}")
    assert resp.status_code == 204
    assert not await _exists(app, "gone-tenant")


async def test_plain_keys_still_delete(app, tenant_client):
    app.state.settings.registry.add(SettingDefinition(key="demo.plain", tenant_overridable=True))
    async with tenant_client() as t:
        await t.client.put("/api/settings/tenant/current/demo.plain", json={"value": "x"})
        assert (await t.client.delete("/api/settings/tenant/current/demo.plain")).status_code == 204
