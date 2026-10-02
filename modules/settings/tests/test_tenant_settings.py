"""Tenant self-service settings and TENANT ``scope_id`` validation (#382).

A tenant owner/admin edits *their own* active tenant's ``tenant_overridable``
keys through ``/api/settings/tenant/current/{key}``; the tenant never comes
from the URL. Platform routes keep editing any scope, but a TENANT ``scope_id``
must name a real tenant.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from settings.constants import INVALIDATION_CHANNEL, PERM_TENANT_EDIT
from settings.contracts.invalidation import parse_invalidation_key
from settings.contracts.registry import SettingDefinition
from settings.contracts.schemas import SettingScope, SettingUpsert, SettingValueType
from settings.deps import SettingsDep
from settings.service import SettingService
from simple_module_core.tenancy import TenantRole, tenant_role

CURRENT = "/api/settings/tenant/current"
KEY = "demo.greeting"
LOCKED = "demo.locked"
COUNT = "demo.count"
CHECKED = "demo.checked"


@pytest.fixture(autouse=True)
def definitions(app):
    registry = app.state.settings.registry

    async def check(request, tenant_id, value):
        if value == "missing":
            raise LookupError("no such thing for this tenant")
        if value == "bad":
            raise ValueError("bad value")

    registry.add(SettingDefinition(key=KEY, default="hello", tenant_overridable=True))
    registry.add(SettingDefinition(key=LOCKED, default="x"))
    registry.add(
        SettingDefinition(
            key=COUNT, default="1", value_type=SettingValueType.INT, tenant_overridable=True
        )
    )
    registry.add(SettingDefinition(key=CHECKED, tenant_overridable=True, check=check))


async def _system(app, key: str, value: str) -> None:
    async with app.state.sm.db.session_factory() as db:
        await SettingService(db).upsert_scoped(
            SettingScope.SYSTEM, "", key, SettingUpsert(value=value)
        )
        await db.commit()


async def _tenant_value(app, tenant_id: str, key: str) -> str | None:
    async with app.state.sm.db.session_factory() as db:
        row = await SettingService(db).get_scoped(SettingScope.TENANT, tenant_id, key)
    return row.value if row is not None else None


def _row(listing: list[dict], key: str) -> dict:
    return next(r for r in listing if r["key"] == key)


class TestPermissionMapping:
    def test_owner_and_admin_hold_it_member_does_not(self, app):
        role_map = app.state.sm.permissions.role_map
        assert PERM_TENANT_EDIT in role_map[tenant_role(TenantRole.OWNER)]
        assert PERM_TENANT_EDIT in role_map[tenant_role(TenantRole.ADMIN)]
        assert PERM_TENANT_EDIT not in role_map.get(tenant_role(TenantRole.MEMBER), [])

    def test_the_unused_tenants_permission_is_retired(self, app):
        names = {p for g in app.state.sm.permissions.groups for p in g.permissions}
        assert "tenants.settings.manage" not in names


class TestSelfService:
    @pytest.mark.parametrize("role", ["owner", "admin"])
    async def test_manager_edits_own_overridable_key(self, app, tenant_client, role):
        async with tenant_client(role) as me:
            resp = await me.client.put(f"{CURRENT}/{KEY}", json={"value": "hi"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["scope"] == "tenant"
            assert resp.json()["scope_id"] == me.tenant_id
            assert (await me.client.get(f"{CURRENT}/{KEY}")).json()["value"] == "hi"
        assert await _tenant_value(app, me.tenant_id, KEY) == "hi"

    async def test_reset_falls_back_and_second_reset_404s(self, tenant_client):
        async with tenant_client() as me:
            await me.client.put(f"{CURRENT}/{KEY}", json={"value": "hi"})
            assert (await me.client.delete(f"{CURRENT}/{KEY}")).status_code == 204
            assert (await me.client.delete(f"{CURRENT}/{KEY}")).status_code == 404
            assert (await me.client.get(f"{CURRENT}/{KEY}")).status_code == 404

    async def test_writes_land_on_the_active_tenant_only(self, app, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            await a.client.put(f"{CURRENT}/{KEY}", json={"value": "from-a"})
            listing = (await b.client.get(CURRENT)).json()
        assert _row(listing, KEY)["value"] is None
        assert await _tenant_value(app, b.tenant_id, KEY) is None

    async def test_cannot_reach_another_tenant_through_the_platform_routes(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            url = f"/api/settings/tenant/{b.tenant_id}/{KEY}"
            assert (await a.client.put(url, json={"value": "x"})).status_code == 403
            assert (await a.client.delete(url)).status_code == 403
            assert (await a.client.get(url)).status_code == 403

    async def test_cannot_edit_system_scope(self, tenant_client):
        async with tenant_client() as me:
            resp = await me.client.put(f"/api/settings/system/{KEY}", json={"value": "x"})
        assert resp.status_code == 403

    async def test_non_overridable_and_unknown_keys_are_refused(self, tenant_client):
        async with tenant_client() as me:
            for key in (LOCKED, "never.declared"):
                assert (
                    await me.client.put(f"{CURRENT}/{key}", json={"value": "x"})
                ).status_code == 422
                assert (await me.client.get(f"{CURRENT}/{key}")).status_code == 422

    async def test_member_is_forbidden(self, tenant_client):
        async with tenant_client("member") as me:
            assert (await me.client.get(CURRENT)).status_code == 403
            assert (await me.client.put(f"{CURRENT}/{KEY}", json={"value": "x"})).status_code == 403

    async def test_no_active_tenant_is_forbidden(self, authenticated_client):
        # The platform admin passes the permission guard but acts for no tenant.
        assert (await authenticated_client.get(CURRENT)).status_code == 403
        resp = await authenticated_client.put(f"{CURRENT}/{KEY}", json={"value": "x"})
        assert resp.status_code == 403

    async def test_declared_type_wins(self, tenant_client):
        async with tenant_client() as me:
            bad = await me.client.put(
                f"{CURRENT}/{COUNT}", json={"value": "abc", "value_type": "string"}
            )
            ok = await me.client.put(f"{CURRENT}/{COUNT}", json={"value": "5"})
        assert bad.status_code == 422
        assert ok.json()["value_type"] == "int"

    async def test_check_hook(self, tenant_client):
        async with tenant_client() as me:
            url = f"{CURRENT}/{CHECKED}"
            assert (await me.client.put(url, json={"value": "missing"})).status_code == 404
            assert (await me.client.put(url, json={"value": "bad"})).status_code == 422
            assert (await me.client.put(url, json={"value": "fine"})).status_code == 200


class TestEffectiveValue:
    async def test_precedence_default_then_system_then_tenant(self, app, tenant_client):
        async with tenant_client() as me:
            row = _row((await me.client.get(CURRENT)).json(), KEY)
            assert (row["inherited"], row["value"], row["effective"]) == ("hello", None, "hello")

            await _system(app, KEY, "sys")
            row = _row((await me.client.get(CURRENT)).json(), KEY)
            assert (row["inherited"], row["effective"]) == ("sys", "sys")

            await me.client.put(f"{CURRENT}/{KEY}", json={"value": "mine"})
            row = _row((await me.client.get(CURRENT)).json(), KEY)
            assert (row["inherited"], row["value"], row["effective"]) == ("sys", "mine", "mine")

    async def test_listing_offers_only_overridable_keys(self, tenant_client):
        async with tenant_client() as me:
            keys = {r["key"] for r in (await me.client.get(CURRENT)).json()}
        assert {KEY, COUNT, CHECKED} <= keys
        assert LOCKED not in keys

    async def test_accessor_reads_the_active_tenant(self, app, tenant_client):
        @app.get("/__greeting")
        async def greeting(request: Request, settings: SettingsDep):
            return {"value": await settings.get(KEY)}

        await _system(app, KEY, "sys")
        async with tenant_client() as a, tenant_client() as b:
            await a.client.put(f"{CURRENT}/{KEY}", json={"value": "mine"})
            assert (await a.client.get("/__greeting")).json() == {"value": "mine"}
            assert (await b.client.get("/__greeting")).json() == {"value": "sys"}


class TestPlatformScopeIdValidation:
    async def test_unknown_tenant_is_404_on_get_and_put(self, authenticated_client):
        url = f"/api/settings/tenant/no-such-tenant/{KEY}"
        assert (await authenticated_client.put(url, json={"value": "x"})).status_code == 404
        assert (await authenticated_client.get(url)).status_code == 404

    async def test_unknown_tenant_in_a_create_body_is_422(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/settings/",
            json={"scope": "tenant", "scope_id": "no-such-tenant", "key": "k", "value": "v"},
        )
        assert resp.status_code == 422

    async def test_delete_stays_unvalidated(self, authenticated_client):
        # Nothing stored, so 404 for the *row* — not a refusal of the id.
        resp = await authenticated_client.delete(f"/api/settings/tenant/gone/{KEY}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Setting not found"

    async def test_real_tenant_is_accepted_and_check_runs(
        self, authenticated_client, tenant_client
    ):
        async with tenant_client() as t:
            url = f"/api/settings/tenant/{t.tenant_id}"
            ok = await authenticated_client.put(f"{url}/{LOCKED}", json={"value": "v"})
            refused = await authenticated_client.put(f"{url}/{CHECKED}", json={"value": "missing"})
        # Platform operators may write non-overridable keys at tenant scope.
        assert ok.status_code == 200
        assert refused.status_code == 404

    async def test_the_edit_form_runs_the_check_on_a_tenant_row(
        self, app, authenticated_client, tenant_client
    ):
        """``PUT /admin/settings/{id}`` is a second door onto a TENANT row: it
        must refuse what the create form and the JSON routes refuse."""
        async with tenant_client() as t:
            async with app.state.sm.db.session_factory() as db:
                row = await SettingService(db).upsert_scoped(
                    SettingScope.TENANT, t.tenant_id, CHECKED, SettingUpsert(value="fine")
                )
                await db.commit()
            url = f"/admin/settings/{row.id}"
            back = {"Referer": f"http://testserver{url}/edit"}

            refused = await authenticated_client.put(url, json={"value": "bad"}, headers=back)
            assert refused.status_code == 303
            assert refused.headers["location"].endswith(f"{url}/edit")
            assert await _tenant_value(app, t.tenant_id, CHECKED) == "fine"

            ok = await authenticated_client.put(url, json={"value": "better"}, headers=back)
            assert ok.headers["location"].endswith("/admin/settings/store")
            assert await _tenant_value(app, t.tenant_id, CHECKED) == "better"


class TestInvalidation:
    async def test_writes_publish_per_tenant_and_key_after_commit(self, app, tenant_client):
        seen: list[tuple[str | None, str | None]] = []
        app.state.sm.invalidation.subscribe(
            INVALIDATION_CHANNEL, lambda inv: seen.append(parse_invalidation_key(inv.key))
        )
        async with tenant_client() as me:
            await me.client.put(f"{CURRENT}/{KEY}", json={"value": "x"})
            await me.client.delete(f"{CURRENT}/{KEY}")
            await me.client.put(f"{CURRENT}/{LOCKED}", json={"value": "x"})  # 422: no write
        assert seen == [(me.tenant_id, KEY), (me.tenant_id, KEY)]

    async def test_system_writes_publish_without_a_tenant(self, app, authenticated_client):
        seen: list[tuple[str | None, str | None]] = []
        app.state.sm.invalidation.subscribe(
            INVALIDATION_CHANNEL, lambda inv: seen.append(parse_invalidation_key(inv.key))
        )
        await authenticated_client.put(f"/api/settings/system/{KEY}", json={"value": "x"})
        assert seen == [(None, KEY)]
