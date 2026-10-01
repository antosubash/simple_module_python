"""Per-tenant branding in shared props, its fallback and its cache (#373).

A tenant's ``branding.<field>`` overrides (settings, TENANT scope) sit on top
of the system theme for requests acting for that tenant; everyone else — and
every request on a host with ``multi_tenant`` off — sees the system theme from
the process-wide object, with no lookup.
"""

from __future__ import annotations

import httpx
import pytest
from branding import tenant_branding
from settings.constants import INVALIDATION_CHANNEL
from settings.contracts.invalidation import invalidation_key
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService
from simple_module_hosting.settings import Settings
from simple_module_test.database import database_url_for_tests

INERTIA = {"X-Inertia": "true", "Accept": "application/json"}
CURRENT = "/api/settings/tenant/current"


@pytest.fixture(autouse=True)
def _fresh_cache():
    tenant_branding.forget()
    yield
    tenant_branding.forget()


async def _branding(client: httpx.AsyncClient, page: str = "/tenants/") -> dict:
    resp = await client.get(page, headers=INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]["branding"]


async def _set(client: httpx.AsyncClient, field: str, value: str) -> httpx.Response:
    return await client.put(f"{CURRENT}/branding.{field}", json={"value": value})


async def _write_row(app, tenant_id: str, field: str, value: str) -> None:
    """Behind the API's back: no invalidation notice is published."""
    async with app.state.sm.db.session_factory() as db:
        await SettingService(db).upsert_scoped(
            SettingScope.TENANT, tenant_id, f"branding.{field}", SettingUpsert(value=value)
        )
        await db.commit()


class TestPerTenantProps:
    async def test_two_tenants_see_their_own_branding(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            assert (await _set(a.client, "app_name", "Acme")).status_code == 200
            assert (await _set(b.client, "app_name", "Beta")).status_code == 200
            await _set(b.client, "primary_color", "#112233")

            got_a, got_b = await _branding(a.client), await _branding(b.client)
        assert (got_a["appName"], got_a["primaryColor"]) == ("Acme", None)
        assert (got_b["appName"], got_b["primaryColor"]) == ("Beta", "#112233")

    async def test_unset_fields_fall_back_to_the_system_theme(
        self, authenticated_client, tenant_client
    ):
        resp = await authenticated_client.put(
            "/api/branding/", json={"app_name": "Platform", "primary_color": "#abcdef"}
        )
        assert resp.status_code == 200, resp.text
        async with tenant_client() as a, tenant_client() as plain:
            await _set(a.client, "app_name", "Acme")
            got_a, got_plain = await _branding(a.client), await _branding(plain.client)
        assert (got_a["appName"], got_a["primaryColor"]) == ("Acme", "#abcdef")
        assert (got_plain["appName"], got_plain["primaryColor"]) == ("Platform", "#abcdef")
        # The platform admin acts for no tenant: the system theme.
        assert (await _branding(authenticated_client))["appName"] == "Platform"

    async def test_a_system_change_reaches_tenants_without_an_override(
        self, authenticated_client, tenant_client
    ):
        async with tenant_client() as a:
            await _branding(a.client)  # warm the cache
            await authenticated_client.put("/api/branding/", json={"app_name": "Renamed"})
            assert (await _branding(a.client))["appName"] == "Renamed"

    async def test_members_see_it_but_cannot_change_it(self, tenant_client):
        async with tenant_client() as owner:
            await _set(owner.client, "app_name", "Acme")
            async with tenant_client("member", tenant_id=owner.tenant_id) as member:
                assert (await _branding(member.client))["appName"] == "Acme"
                assert (await _set(member.client, "app_name", "Mine")).status_code == 403

    @pytest.mark.parametrize(
        ("field", "value"),
        [("primary_color", "red"), ("app_name", "  "), ("design_pack", "no-such-pack")],
    )
    async def test_invalid_values_are_refused(self, tenant_client, field, value):
        async with tenant_client() as a:
            assert (await _set(a.client, field, value)).status_code == 422

    async def test_platform_only_fields_are_not_overridable(self, tenant_client):
        async with tenant_client() as a:
            assert (await _set(a.client, "banner_message", "hi")).status_code == 422
            assert (await _set(a.client, "footer_links", "[]")).status_code == 422

    async def test_a_hand_edited_bad_row_degrades_to_the_system_value(self, app, tenant_client):
        async with tenant_client() as a:
            await _write_row(app, a.tenant_id, "primary_color", "not-a-colour")
            await _write_row(app, a.tenant_id, "app_name", "Fine")
            got = await _branding(a.client)
        assert (got["appName"], got["primaryColor"]) == ("Fine", None)

    async def test_the_head_shows_the_tenants_name(self, tenant_client):
        async with tenant_client() as a:
            await _set(a.client, "app_name", "Acme Head")
            html = (await a.client.get("/tenants/")).text
        assert "<title" in html and "Acme Head" in html


class TestCacheInvalidation:
    async def test_a_tenant_notice_forgets_only_that_tenant(self, app, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            await _branding(a.client), await _branding(b.client)
            await _write_row(app, a.tenant_id, "app_name", "Quiet A")
            await _write_row(app, b.tenant_id, "app_name", "Quiet B")
            # Cached: a write that published nothing is not seen yet...
            assert (await _branding(a.client))["appName"] != "Quiet A"

            bus = app.state.sm.invalidation
            await bus.publish(INVALIDATION_CHANNEL, key=invalidation_key(a.tenant_id, "x.y"))
            assert (await _branding(a.client))["appName"] != "Quiet A"  # not a branding key

            await bus.publish(
                INVALIDATION_CHANNEL, key=invalidation_key(a.tenant_id, "branding.app_name")
            )
            assert (await _branding(a.client))["appName"] == "Quiet A"
            assert (await _branding(b.client))["appName"] != "Quiet B"

            # A system value is inherited by everyone: its notice forgets all.
            await bus.publish(INVALIDATION_CHANNEL, key=invalidation_key(None, "branding.app_name"))
            assert (await _branding(b.client))["appName"] == "Quiet B"

    async def test_a_notice_from_another_worker_is_applied(self, app, tenant_client):
        from simple_module_core.invalidation import Invalidation

        async with tenant_client() as a:
            await _branding(a.client)
            await _write_row(app, a.tenant_id, "app_name", "Remote")
            wire = Invalidation(
                INVALIDATION_CHANNEL,
                key=invalidation_key(a.tenant_id, "branding.app_name"),
                origin="another-worker",
            ).to_wire()
            await app.state.sm.invalidation.deliver(wire)
            assert (await _branding(a.client))["appName"] == "Remote"

    async def test_writes_through_the_api_are_seen_at_once(self, tenant_client):
        async with tenant_client() as a:
            await _set(a.client, "app_name", "One")
            assert (await _branding(a.client))["appName"] == "One"
            await _set(a.client, "app_name", "Two")
            assert (await _branding(a.client))["appName"] == "Two"
            await a.client.delete(f"{CURRENT}/branding.app_name")
            assert (await _branding(a.client))["appName"] == "SimpleModule"


class TestSingleTenantInstall:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            database_url=database_url_for_tests(),
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            auth_provider="users",
        )

    async def test_branding_is_the_system_theme_with_no_lookup(
        self, app, authenticated_client, monkeypatch
    ):
        async def no_lookup(*_args, **_kwargs):
            raise AssertionError("multi_tenant off must not read tenant overrides")

        monkeypatch.setattr(tenant_branding, "read_overrides", no_lookup)
        await _write_row(app, "default", "app_name", "Should not show")
        await authenticated_client.put("/api/branding/", json={"app_name": "Single"})

        got = await _branding(authenticated_client, "/admin/branding/")
        assert got["appName"] == "Single"


async def test_tenant_rows_carry_a_description_key_for_the_client(tenant_client):
    async with tenant_client() as a:
        rows = (await a.client.get(CURRENT)).json()
    mine = {r["key"]: r for r in rows if r["key"].startswith("branding.")}
    assert mine["branding.app_name"]["description_key"] == "branding.tenant_settings.app_name"
    assert mine["branding.app_name"]["description"]  # the English fallback
