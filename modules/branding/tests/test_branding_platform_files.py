"""Branding images are *platform* files, against the real file_storage (#383).

``StoredFile`` is tenant-scoped and the suite runs strict, yet the logo must
load for an anonymous visitor (no tenant bound at all) and must not land in —
or be deletable from — whichever organisation the uploading admin has active.
Branding therefore uploads, serves and reaps with ``platform=True``: rows owned
by ``PLATFORM_TENANT_ID``, read under ``all_tenants()`` but only ever matching
that owner.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from branding.constants import LOGO_URL
from file_storage.models import StoredFile
from file_storage.scope import PLATFORM_TENANT_ID
from simple_module_db import all_tenants
from sqlalchemy import select

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def _upload_logo(client: httpx.AsyncClient, body: bytes = _PNG) -> None:
    resp = await client.post("/api/branding/logo", files={"file": ("logo.png", body, "image/png")})
    assert resp.status_code == 200, resp.text


async def _rows(app) -> list[StoredFile]:
    with all_tenants():
        async with app.state.sm.db.session_factory() as session:
            stmt = select(StoredFile).execution_options(include_deleted=True)
            return list((await session.execute(stmt)).scalars().all())


async def _give_admin_a_tenant(app) -> str:
    from simple_module_test.fixtures import SETUP_ADMIN_EMAIL
    from tenants.models import Membership, Tenant
    from tenants.resolver import forget
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        admin = (
            await session.execute(select(User).where(User.email == SETUP_ADMIN_EMAIL))
        ).scalar_one()
        tenant = Tenant(slug="admin-org", name="Admin Org")
        session.add(tenant)
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=str(admin.id), role="owner"))
        await session.commit()
        forget(str(admin.id))
        return tenant.id


async def test_a_platform_admin_with_no_tenant_can_brand_and_guests_see_it(
    app, authenticated_client: httpx.AsyncClient, client: httpx.AsyncClient
):
    await _upload_logo(authenticated_client)

    [row] = await _rows(app)
    assert row.tenant_id == PLATFORM_TENANT_ID
    assert row.key.startswith(f"{PLATFORM_TENANT_ID}/")

    resp = await client.get(LOGO_URL)  # anonymous, no tenant bound
    assert resp.status_code == 200, resp.text
    assert resp.content == _PNG


async def test_an_admin_inside_a_tenant_still_uploads_a_platform_file(
    app, authenticated_client: httpx.AsyncClient, client: httpx.AsyncClient
):
    await _give_admin_a_tenant(app)
    await _upload_logo(authenticated_client)

    [row] = await _rows(app)
    assert row.tenant_id == PLATFORM_TENANT_ID
    # Not one of the organisation's files: absent from its listing...
    listed = (await authenticated_client.get("/api/file-storage/files")).json()
    assert listed["items"] == []
    # ...and unreachable through its routes.
    resp = await authenticated_client.get(f"/api/file-storage/files/{row.id}")
    assert resp.status_code == 404
    assert (await client.get(LOGO_URL)).status_code == 200


async def test_replacing_the_logo_reaps_the_old_platform_file(
    app, authenticated_client: httpx.AsyncClient
):
    await _give_admin_a_tenant(app)
    await _upload_logo(authenticated_client, _PNG)
    await _upload_logo(authenticated_client, _PNG + b"\x01")

    rows = sorted(await _rows(app), key=lambda r: r.created_at)
    assert [r.is_deleted for r in rows] == [True, False]


async def test_a_setting_naming_a_tenant_file_cannot_publish_it(
    app, tenant_client, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The settings store is editable; pointing ``logo_file_id`` at a tenant's
    upload must not turn the anonymous logo route into a download link for it."""
    async with tenant_client() as tenant:
        resp = await tenant.client.post(
            "/api/file-storage/upload", files={"file": ("secret.png", _PNG, "image/png")}
        )
        assert resp.status_code == 201, resp.text
        file_id = resp.json()["id"]

    monkeypatch.setattr(app.state.branding.settings, "logo_file_id", file_id)

    assert (await client.get(LOGO_URL)).status_code == 404
    monkeypatch.setattr(app.state.branding.settings, "logo_file_id", str(uuid.uuid4()))
    assert (await client.get(LOGO_URL)).status_code == 404
