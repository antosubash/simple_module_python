"""A replaced branding image is reaped after commit, and only when unreferenced.

Deleting in the request removed the bytes before the settings write was
durable: a rollback left the setting pointing at a deleted file. And a file
another image field of the same owner still holds must survive.
"""

from __future__ import annotations

import pytest
from branding import tenant_branding
from branding.endpoints import tenant_api
from branding.service import BrandingService
from file_storage.models import StoredFile
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService
from simple_module_db import all_tenants
from sqlalchemy import select

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TENANT_LOGO = "/api/branding/tenant/logo"


@pytest.fixture(autouse=True)
def _fresh_cache():
    tenant_branding.forget()
    yield
    tenant_branding.forget()


async def _upload(client, url: str = TENANT_LOGO, body: bytes = _PNG) -> None:
    resp = await client.post(url, files={"file": ("logo.png", body, "image/png")})
    assert resp.status_code == 200, resp.text


async def _deleted(app) -> dict[str, bool]:
    with all_tenants():
        async with app.state.sm.db.session_factory() as db:
            stmt = select(StoredFile).execution_options(include_deleted=True)
            return {str(r.id): r.is_deleted for r in (await db.execute(stmt)).scalars()}


async def _tenant_value(app, tenant_id: str, key: str) -> str | None:
    async with app.state.sm.db.session_factory() as db:
        row = await SettingService(db).get_scoped(SettingScope.TENANT, tenant_id, key)
    return row.value if row is not None else None


async def test_a_rolled_back_replace_keeps_the_old_file(app, tenant_client, monkeypatch):
    async with tenant_client() as a:
        await _upload(a.client)
        old = await _tenant_value(app, a.tenant_id, "branding.logo_file_id")

        def boom(*_a, **_k):
            raise RuntimeError("late failure after the swap")

        monkeypatch.setattr(tenant_api, "merge", boom)
        with pytest.raises(RuntimeError):
            await _upload(a.client, body=_PNG + b"new")

        assert await _tenant_value(app, a.tenant_id, "branding.logo_file_id") == old
        assert (await _deleted(app))[old] is False
        monkeypatch.undo()
        assert (await a.client.get("/api/branding/logo")).content == _PNG


async def test_a_tenant_file_another_field_still_uses_is_kept(app, tenant_client):
    async with tenant_client() as a:
        await _upload(a.client)
        shared = await _tenant_value(app, a.tenant_id, "branding.logo_file_id")
        # A hand-edited (or migrated) row sharing the logo's file.
        async with app.state.sm.db.session_factory() as db:
            await SettingService(db).upsert_scoped(
                SettingScope.TENANT,
                a.tenant_id,
                "branding.logo_dark_file_id",
                SettingUpsert(value=shared),
            )
            await db.commit()

        await _upload(a.client, body=_PNG + b"new")
        assert (await _deleted(app))[shared] is False

        cleared = await a.client.delete("/api/branding/tenant/logo-dark")
        assert cleared.status_code == 200
        assert (await _deleted(app))[shared] is True


async def test_a_platform_file_another_system_field_still_uses_is_kept(app, authenticated_client):
    await _upload(authenticated_client, "/api/branding/logo")
    shared = app.state.branding.settings.logo_file_id
    async with app.state.sm.db.session_factory() as db:
        await BrandingService(app, db).apply({"logo_dark_file_id": shared})
        await db.commit()

    await _upload(authenticated_client, "/api/branding/logo", _PNG + b"new")
    assert (await _deleted(app))[shared] is False

    assert (await authenticated_client.delete("/api/branding/logo-dark")).status_code == 200
    assert (await _deleted(app))[shared] is True
