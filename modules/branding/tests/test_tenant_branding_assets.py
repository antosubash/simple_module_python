"""Tenant-owned branding images: upload, serve, subdomain, ownership (#373).

A tenant's logo is a file in *its own* ``file_storage`` namespace (never a
platform file), served by the anonymous asset routes only to requests resolved
to that tenant — a member's session or the tenant's subdomain — and only while
the file is the tenant's. No route takes a file id from the request.
"""

from __future__ import annotations

import httpx
import pytest
from branding import tenant_branding
from branding.constants import LOGO_URL
from file_storage.models import StoredFile
from file_storage.scope import PLATFORM_TENANT_ID
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.service import SettingService
from simple_module_db import all_tenants
from sqlalchemy import select
from tenants.host_resolver import forget_hosts
from tenants.models import Tenant

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TENANT_LOGO = "/api/branding/tenant/logo"
CURRENT = "/api/settings/tenant/current"


@pytest.fixture(autouse=True)
def _fresh_cache(app):
    tenant_branding.forget(app)
    yield
    tenant_branding.forget(app)


async def _upload(client: httpx.AsyncClient, body: bytes = _PNG) -> dict:
    resp = await client.post(TENANT_LOGO, files={"file": ("logo.png", body, "image/png")})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _files(app) -> list[StoredFile]:
    with all_tenants():
        async with app.state.sm.db.session_factory() as db:
            stmt = select(StoredFile).execution_options(include_deleted=True)
            return sorted((await db.execute(stmt)).scalars().all(), key=lambda r: r.created_at)


async def _plain_upload(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/api/file-storage/upload", files={"file": ("x.png", _PNG, "image/png")}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestUploadAndServe:
    async def test_the_upload_is_the_tenants_file_and_only_it_sees_it(self, app, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            out = await _upload(a.client)
            [row] = await _files(app)
            assert row.tenant_id == a.tenant_id
            assert out["logo_url"] == f"{LOGO_URL}?v={row.id}"

            resp = await a.client.get(out["logo_url"])
            assert resp.status_code == 200
            assert resp.content == _PNG
            # Private: the same URL answers differently for another tenant.
            assert resp.headers["cache-control"].startswith("private")
            assert "immutable" in resp.headers["cache-control"]
            assert "Cookie" in resp.headers["vary"]

            assert (await b.client.get(LOGO_URL)).status_code == 404  # no system logo

    async def test_a_platform_admin_upload_is_still_a_platform_file(
        self, app, authenticated_client, tenant_client
    ):
        await authenticated_client.post(
            "/api/branding/logo", files={"file": ("p.png", _PNG + b"p", "image/png")}
        )
        async with tenant_client() as a:
            # The tenant has no logo of its own: it inherits the platform's.
            resp = await a.client.get(LOGO_URL)
            assert resp.content == _PNG + b"p"
            # Even the platform's file: the request has a tenant, so a shared
            # cache must not serve this answer to the tenant-less URL.
            assert resp.headers["cache-control"] == "private, no-cache"
            await _upload(a.client)
            assert (await a.client.get(LOGO_URL)).content == _PNG
        owners = {r.tenant_id for r in await _files(app)}
        assert owners == {PLATFORM_TENANT_ID, a.tenant_id}

    async def test_replacing_and_clearing_reap_the_tenants_old_file(self, app, tenant_client):
        async with tenant_client() as a:
            await _upload(a.client, _PNG)
            await _upload(a.client, _PNG + b"\x01")
            cleared = await a.client.delete(TENANT_LOGO)
            assert cleared.status_code == 200
            assert cleared.json()["logo_url"] is None
            assert (await a.client.get(LOGO_URL)).status_code == 404
        assert [r.is_deleted for r in await _files(app)] == [True, True]

    async def test_a_deleted_tenant_logo_falls_back_to_the_platform_logo(
        self, app, authenticated_client, tenant_client
    ):
        """qa BUG-005: deleting the file via Files left a dangling override that 404'd."""
        await authenticated_client.post(
            "/api/branding/logo", files={"file": ("p.png", _PNG + b"p", "image/png")}
        )
        async with tenant_client() as a:
            out = await _upload(a.client)
            [_, row] = await _files(app)
            gone = await a.client.delete(f"/api/file-storage/files/{row.id}")
            assert gone.status_code == 204, gone.text
            tenant_branding.forget(app)

            resp = await a.client.get(out["logo_url"])  # the tenant's now-dead URL
            assert resp.status_code == 200
            assert resp.content == _PNG + b"p"
            assert resp.headers["cache-control"] == "private, no-cache"

    async def test_member_cannot_upload(self, tenant_client):
        async with (
            tenant_client() as owner,
            tenant_client("member", tenant_id=owner.tenant_id) as member,
        ):
            resp = await member.client.post(
                TENANT_LOGO, files={"file": ("l.png", _PNG, "image/png")}
            )
        assert resp.status_code == 403

    async def test_unknown_asset_is_404(self, tenant_client):
        async with tenant_client() as a:
            resp = await a.client.post(
                "/api/branding/tenant/banner", files={"file": ("l.png", _PNG, "image/png")}
            )
        assert resp.status_code == 404


class TestSubdomain:
    @pytest.fixture
    def subdomains(self, app):
        app.state.tenants.settings.subdomain_base = "example.com"
        forget_hosts()
        yield
        app.state.tenants.settings.subdomain_base = ""
        forget_hosts()

    async def test_an_anonymous_visitor_gets_that_tenants_logo(
        self, app, subdomains, tenant_client
    ):
        async with tenant_client() as a:
            await _upload(a.client)
        async with app.state.sm.db.session_factory() as db:
            slug = (await db.get(Tenant, a.tenant_id)).slug

        def anon(host: str) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=host)

        async with anon(f"http://{slug}.example.com") as visitor:
            resp = await visitor.get(LOGO_URL)
            assert resp.status_code == 200
            assert resp.content == _PNG
        async with anon("http://example.com") as visitor:
            assert (await visitor.get(LOGO_URL)).status_code == 404  # the system's: none


class TestGenericRoutesRefuseImageKeys:
    """Images go through ``/api/branding/tenant/{asset}`` only: a generic
    settings write could point the logo at any file (a PDF, another tenant's
    upload, a platform file) and would never reap the file it displaced."""

    async def test_self_service_writes_are_422_whatever_the_value(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            theirs = await _plain_upload(b.client)
            ours = await _plain_upload(a.client)
            key = f"{CURRENT}/branding.logo_file_id"
            for value in (theirs, ours, "not-a-uuid", ""):
                resp = await a.client.put(key, json={"value": value})
                assert resp.status_code == 422, value
                assert "/api/branding/tenant/logo" in resp.json()["detail"]
            assert (await a.client.get(LOGO_URL)).status_code == 404

    async def test_nor_can_it_name_a_platform_file(self, app, authenticated_client, tenant_client):
        await authenticated_client.post(
            "/api/branding/logo", files={"file": ("p.png", _PNG, "image/png")}
        )
        platform_id = str(app.state.branding.settings.logo_file_id)
        async with tenant_client() as a:
            resp = await a.client.put(
                f"{CURRENT}/branding.logo_file_id", json={"value": platform_id}
            )
        assert resp.status_code == 422

    async def test_a_platform_operator_writing_for_a_tenant_is_refused_too(
        self, authenticated_client, tenant_client
    ):
        async with tenant_client() as a:
            ours = await _plain_upload(a.client)
            url = f"/api/settings/tenant/{a.tenant_id}/branding.favicon_file_id"
            assert (await authenticated_client.put(url, json={"value": ours})).status_code == 422


class TestOwnership:
    async def test_a_hand_edited_row_naming_another_tenants_file_serves_404(
        self, app, tenant_client
    ):
        async with tenant_client() as a, tenant_client() as b:
            theirs = await _plain_upload(b.client)
            async with app.state.sm.db.session_factory() as db:
                await SettingService(db).upsert_scoped(
                    SettingScope.TENANT,
                    a.tenant_id,
                    "branding.logo_file_id",
                    SettingUpsert(value=theirs),
                )
                await db.commit()
            assert (await a.client.get(LOGO_URL)).status_code == 404
            assert (await b.client.get(f"/api/file-storage/files/{theirs}")).status_code == 200


class TestCacheHeaders:
    """Only a tenant-less request whose ``?v=`` names the served file is public."""

    async def test_a_platform_logo_on_a_tenant_request_is_never_public(
        self, app, authenticated_client, tenant_client
    ):
        await authenticated_client.post(
            "/api/branding/logo", files={"file": ("p.png", _PNG, "image/png")}
        )
        versioned = f"{LOGO_URL}?v={app.state.branding.settings.logo_file_id}"
        async with tenant_client() as a:
            resp = await a.client.get(versioned)
        assert resp.headers["cache-control"].startswith("private")
        assert "immutable" in resp.headers["cache-control"]
        assert {"Cookie", "X-Tenant-ID"} <= {v.strip() for v in resp.headers["vary"].split(",")}

    async def test_a_stale_version_on_a_tenant_request_is_no_cache(self, tenant_client):
        async with tenant_client() as a:
            out = await _upload(a.client)
            await _upload(a.client, _PNG + b"2")
            resp = await a.client.get(out["logo_url"])  # names the replaced file
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "private, no-cache"

    async def test_the_tenant_header_is_part_of_vary(self, app, tenant_client, monkeypatch):
        monkeypatch.setattr(app.state.sm.settings, "tenant_header", "X-Tenant")
        async with tenant_client() as a:
            out = await _upload(a.client)
            resp = await a.client.get(out["logo_url"])
        assert "X-Tenant" in {v.strip() for v in resp.headers["vary"].split(",")}

    async def test_an_anonymous_versioned_platform_logo_is_public(
        self, app, authenticated_client, client
    ):
        await authenticated_client.post(
            "/api/branding/logo", files={"file": ("p.png", _PNG, "image/png")}
        )
        versioned = f"{LOGO_URL}?v={app.state.branding.settings.logo_file_id}"
        resp = await client.get(versioned)
        assert resp.headers["cache-control"].startswith("public")
        assert "X-Tenant-ID" not in resp.headers.get("vary", "")


class TestOnlyImagesAreServed:
    async def test_a_setting_naming_a_non_image_file_serves_404(self, app, tenant_client):
        async with tenant_client() as a:
            resp = await a.client.post(
                "/api/file-storage/upload",
                files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            )
            pdf = resp.json()["id"]
            async with app.state.sm.db.session_factory() as db:
                await SettingService(db).upsert_scoped(
                    SettingScope.TENANT,
                    a.tenant_id,
                    "branding.logo_file_id",
                    SettingUpsert(value=pdf),
                )
                await db.commit()
            tenant_branding.forget(app)
            assert (await a.client.get(LOGO_URL)).status_code == 404
