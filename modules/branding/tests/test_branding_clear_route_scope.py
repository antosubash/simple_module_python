"""The managed-key refusal names the route that clears the row's own scope (ship qa r2).

The system logo is removed through ``DELETE /api/branding/logo``; the tenant
route cannot touch it, so pointing a SYSTEM-scope refusal there was a dead end.
"""

from __future__ import annotations

from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService

KEY = "branding.logo_file_id"
SYSTEM_ROUTE = "/api/branding/logo"
TENANT_ROUTE = "/api/branding/tenant/logo"
CURRENT = "/api/settings/tenant/current"


async def test_system_scope_refusal_names_the_system_route(app, authenticated_client):
    async with app.state.sm.db.session_factory() as db:
        await SettingService(db).upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, KEY, SettingUpsert(value="1")
        )
        await db.commit()
    resp = await authenticated_client.delete(f"/api/settings/system/{KEY}")
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert SYSTEM_ROUTE in detail
    assert TENANT_ROUTE not in detail
    assert resp.json()["clear_via"] == SYSTEM_ROUTE


async def test_tenant_scope_refusal_names_the_tenant_route(app, tenant_client):
    async with tenant_client() as t:
        async with app.state.sm.db.session_factory() as db:
            await SettingService(db).upsert_scoped(
                SettingScope.TENANT, t.tenant_id, KEY, SettingUpsert(value="1")
            )
            await db.commit()
        resp = await t.client.delete(f"{CURRENT}/{KEY}")
        assert resp.status_code == 422, resp.text
        assert resp.json()["clear_via"] == TENANT_ROUTE
