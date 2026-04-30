"""REST API tests for feature_flags — system + tenant scope endpoints."""

from __future__ import annotations

import httpx


class TestFeatureFlagsAPI:
    async def test_list_flags_returns_registered_flags(
        self, authenticated_client: httpx.AsyncClient
    ):
        # file_storage module registers `file_storage.public_uploads`
        resp = await authenticated_client.get("/api/feature_flags/")
        assert resp.status_code == 200
        names = {f["name"] for f in resp.json()}
        assert "file_storage.public_uploads" in names

    async def test_set_override_flips_flag(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            "/api/feature_flags/file_storage.public_uploads",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "file_storage.public_uploads"
        assert body["enabled"] is True
        assert body["overridden"] is True

    async def test_set_override_unknown_flag_404s(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            "/api/feature_flags/does.not.exist",
            json={"enabled": True},
        )
        assert resp.status_code == 404

    async def test_clear_override_reverts_to_default(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(
            "/api/feature_flags/file_storage.public_uploads",
            json={"enabled": True},
        )
        resp = await authenticated_client.delete("/api/feature_flags/file_storage.public_uploads")
        assert resp.status_code == 204

        follow = await authenticated_client.get("/api/feature_flags/file_storage.public_uploads")
        assert follow.status_code == 200
        assert follow.json()["overridden"] is False

    async def test_clear_override_without_any_404s(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/api/feature_flags/file_storage.public_uploads")
        assert resp.status_code == 404

    async def test_get_flag_returns_view(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/feature_flags/file_storage.public_uploads")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "file_storage.public_uploads"
        assert "default_enabled" in body
        assert "overridden" in body


class TestFeatureFlagsTenantAPI:
    async def test_set_tenant_override_creates_tenant_specific_row(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.put(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "file_storage.public_uploads"
        assert body["enabled"] is True
        assert body["overridden"] is True  # acme has its own row

    async def test_tenant_override_does_not_leak_into_system_view(
        self, authenticated_client: httpx.AsyncClient
    ):
        await authenticated_client.put(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads",
            json={"enabled": True},
        )
        resp = await authenticated_client.get("/api/feature_flags/file_storage.public_uploads")
        assert resp.status_code == 200
        # System view: no tenant_id → tenant override is invisible
        assert resp.json()["overridden"] is False

    async def test_list_for_tenant_shows_tenant_resolution(
        self, authenticated_client: httpx.AsyncClient
    ):
        # System on, tenant off → tenant view should report enabled=False
        await authenticated_client.put(
            "/api/feature_flags/file_storage.public_uploads",
            json={"enabled": True},
        )
        await authenticated_client.put(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads",
            json={"enabled": False},
        )
        resp = await authenticated_client.get("/api/feature_flags/tenant/acme")
        assert resp.status_code == 200
        flag = next(f for f in resp.json() if f["name"] == "file_storage.public_uploads")
        assert flag["enabled"] is False
        assert flag["overridden"] is True
        assert flag["system_enabled"] is True

    async def test_clear_tenant_override_reverts_to_system(
        self, authenticated_client: httpx.AsyncClient
    ):
        await authenticated_client.put(
            "/api/feature_flags/file_storage.public_uploads",
            json={"enabled": True},
        )
        await authenticated_client.put(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads",
            json={"enabled": False},
        )
        resp = await authenticated_client.delete(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads"
        )
        assert resp.status_code == 204

        follow = await authenticated_client.get("/api/feature_flags/tenant/acme")
        flag = next(f for f in follow.json() if f["name"] == "file_storage.public_uploads")
        assert flag["enabled"] is True  # back to system value
        assert flag["overridden"] is False

    async def test_clear_tenant_override_without_any_404s(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.delete(
            "/api/feature_flags/tenant/acme/file_storage.public_uploads"
        )
        assert resp.status_code == 404

    async def test_set_tenant_override_unknown_flag_404s(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.put(
            "/api/feature_flags/tenant/acme/does.not.exist",
            json={"enabled": True},
        )
        assert resp.status_code == 404
