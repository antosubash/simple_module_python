"""Ship-review fixes for tenant branding: merge pairing, empty overrides, the
per-app cache, system-save invalidation and generic deletes of image keys."""

from __future__ import annotations

import httpx
from branding import tenant_branding
from branding.services import BrandingServices
from branding.settings import BrandingSettings
from branding.tenant_branding import TenantCache, merge
from settings.constants import INVALIDATION_CHANNEL
from settings.contracts.invalidation import parse_invalidation_key
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService
from simple_module_db import all_tenants
from sqlalchemy import select

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TENANT_LOGO = "/api/branding/tenant/logo"
CURRENT = "/api/settings/tenant/current"


def _system() -> BrandingSettings:
    return BrandingSettings(
        app_name="Platform",
        primary_color="#112233",
        footer_text="Platform footer",
        logo_file_id="sys-logo",
        logo_dark_file_id="sys-dark",
    )


class TestMergePairing:
    def test_tenant_logo_without_dark_does_not_inherit_the_platform_dark_logo(self):
        got = merge(_system(), "t", {"logo_file_id": "t-logo"}).settings
        assert got.logo_file_id == "t-logo"
        assert got.logo_dark_file_id == ""  # dark surfaces fall back to t-logo

    def test_tenant_dark_logo_alone_keeps_the_platform_light_logo(self):
        got = merge(_system(), "t", {"logo_dark_file_id": "t-dark"}).settings
        assert (got.logo_file_id, got.logo_dark_file_id) == ("sys-logo", "t-dark")

    def test_both_overridden(self):
        got = merge(_system(), "t", {"logo_file_id": "a", "logo_dark_file_id": "b"}).settings
        assert (got.logo_file_id, got.logo_dark_file_id) == ("a", "b")

    def test_no_logo_override_inherits_both(self):
        got = merge(_system(), "t", {"app_name": "Acme"}).settings
        assert (got.logo_file_id, got.logo_dark_file_id) == ("sys-logo", "sys-dark")


class TestEmptyOverrideInherits:
    def test_empty_string_is_unset(self):
        resolved = merge(
            _system(), "t", {"footer_text": "", "primary_color": "", "app_name": "Acme"}
        )
        assert resolved.settings.footer_text == "Platform footer"
        assert resolved.settings.primary_color == "#112233"
        assert resolved.settings.app_name == "Acme"
        assert resolved.tenant_fields == frozenset({"app_name"})

    def test_empty_logo_override_does_not_blank_the_dark_pairing(self):
        got = merge(_system(), "t", {"logo_file_id": ""}).settings
        assert (got.logo_file_id, got.logo_dark_file_id) == ("sys-logo", "sys-dark")


class TestPerAppCache:
    def test_each_services_object_owns_its_cache(self):
        a = BrandingServices(settings=_system())
        b = BrandingServices(settings=_system())
        assert isinstance(a.tenant_cache, TenantCache)
        assert a.tenant_cache is not b.tenant_cache

    async def test_forget_touches_only_that_app(self, app):
        class _Other:
            class state:  # noqa: N801
                branding = BrandingServices(settings=_system())

        other = _Other
        for target in (app, other):
            cache = target.state.branding.tenant_cache
            cache.entries["acme"] = ({}, _system(), None)  # type: ignore[assignment]
        tenant_branding.forget(app, "acme")
        assert "acme" not in app.state.branding.tenant_cache.entries
        assert "acme" in other.state.branding.tenant_cache.entries


async def test_a_system_theme_save_publishes_the_invalidation(app, authenticated_client):
    seen: list[tuple[str | None, str | None]] = []
    app.state.sm.invalidation.subscribe(
        INVALIDATION_CHANNEL, lambda inv: seen.append(parse_invalidation_key(inv.key))
    )
    resp = await authenticated_client.put("/api/branding/", json={"app_name": "Published"})
    assert resp.status_code == 200, resp.text
    assert (None, "branding.app_name") in seen


async def _logo_row(app, tenant_id: str):
    async with app.state.sm.db.session_factory() as db:
        return await SettingService(db).get_scoped(
            SettingScope.TENANT, tenant_id, "branding.logo_file_id"
        )


async def _upload(client: httpx.AsyncClient) -> None:
    resp = await client.post(TENANT_LOGO, files={"file": ("logo.png", _PNG, "image/png")})
    assert resp.status_code == 200, resp.text


async def test_generic_delete_of_an_image_key_is_refused_and_leaks_nothing(
    app, authenticated_client, tenant_client
):
    from file_storage.models import StoredFile

    async with tenant_client() as a:
        await _upload(a.client)
        key = "branding.logo_file_id"
        refused = await a.client.delete(f"{CURRENT}/{key}")
        assert refused.status_code == 422
        assert TENANT_LOGO in refused.json()["detail"]
        platform = await authenticated_client.delete(f"/api/settings/tenant/{a.tenant_id}/{key}")
        assert platform.status_code == 422
        row = await _logo_row(app, a.tenant_id)
        assert row is not None
        with all_tenants():
            async with app.state.sm.db.session_factory() as db:
                ids = (await db.execute(select(StoredFile.id))).scalars().all()
        assert row.value in {str(i) for i in ids}  # row and file both still there

        # The branding route is what clears it, and reaps.
        assert (await a.client.delete(TENANT_LOGO)).status_code in (200, 204)
        assert await _logo_row(app, a.tenant_id) is None


async def test_platform_can_clear_a_leftover_row_of_a_deleted_tenant(app, authenticated_client):
    async with app.state.sm.db.session_factory() as db:
        await SettingService(db).upsert_scoped(
            SettingScope.TENANT, "gone", "branding.logo_file_id", SettingUpsert(value="f")
        )
        await db.commit()
    resp = await authenticated_client.delete("/api/settings/tenant/gone/branding.logo_file_id")
    assert resp.status_code == 204
    assert await _logo_row(app, "gone") is None
