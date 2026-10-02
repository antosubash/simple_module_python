"""``clear_via`` may differ per scope, and the refusal names the row's own route."""

from __future__ import annotations

import pytest
from settings._managed_keys import ManagedKeyError
from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.registry import SettingDefinition, clear_route
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService

KEY = "demo.scoped_logo"
SYSTEM_ROUTE = "/api/demo/logo"
TENANT_ROUTE = "/api/demo/tenant/logo"


def test_clear_route_resolution():
    plain = SettingDefinition(key="a", clear_via=TENANT_ROUTE)
    mapped = SettingDefinition(
        key="b",
        clear_via={SettingScope.SYSTEM: SYSTEM_ROUTE, SettingScope.TENANT: TENANT_ROUTE},
    )
    assert clear_route(plain, SettingScope.SYSTEM) == TENANT_ROUTE
    assert clear_route(mapped, SettingScope.SYSTEM) == SYSTEM_ROUTE
    assert clear_route(mapped, "tenant") == TENANT_ROUTE
    assert clear_route(mapped, SettingScope.USER) == SYSTEM_ROUTE
    assert clear_route(SettingDefinition(key="c"), SettingScope.SYSTEM) == ""


@pytest.fixture(autouse=True)
def definitions(app):
    app.state.settings.registry.add(
        SettingDefinition(
            key=KEY,
            tenant_overridable=True,
            clear_via={SettingScope.SYSTEM: SYSTEM_ROUTE, SettingScope.TENANT: TENANT_ROUTE},
        )
    )


async def test_system_refusal_names_the_system_route(app, authenticated_client):
    async with app.state.sm.db.session_factory() as db:
        await SettingService(db).upsert_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, KEY, SettingUpsert(value="f")
        )
        await db.commit()
    async with app.state.sm.db.session_factory() as db:
        service = SettingService(db, registry=app.state.settings.registry)
        with pytest.raises(ManagedKeyError) as err:
            await service.delete_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, KEY)
        assert err.value.clear_via == SYSTEM_ROUTE


async def test_tenant_refusal_names_the_tenant_route(app, tenant_client):
    async with tenant_client() as t:
        async with app.state.sm.db.session_factory() as db:
            await SettingService(db).upsert_scoped(
                SettingScope.TENANT, t.tenant_id, KEY, SettingUpsert(value="f")
            )
            await db.commit()
        resp = await t.client.delete(f"/api/settings/tenant/current/{KEY}")
        assert resp.status_code == 422
        assert TENANT_ROUTE in resp.json()["detail"]
        assert SYSTEM_ROUTE not in resp.json()["detail"]
