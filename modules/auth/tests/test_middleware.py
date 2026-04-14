"""Tests for AuthMiddleware: redirects, public paths, authenticated access."""

from __future__ import annotations

import httpx


class TestAuthMiddleware:
    async def test_unauthenticated_request_redirects(self, client: httpx.AsyncClient):
        """Accessing a protected page without a session should redirect to /auth/login."""
        resp = await client.get("/dashboard/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_public_paths_not_redirected(self, client: httpx.AsyncClient):
        """Health and auth paths should be accessible without authentication."""
        resp = await client.get("/health")
        assert resp.status_code != 302

    async def test_auth_me_unauthenticated(self, client: httpx.AsyncClient):
        """/auth/me should return authenticated:false when no session."""
        resp = await client.get("/auth/me")
        assert resp.status_code != 302
        data = resp.json()
        assert data["authenticated"] is False

    async def test_authenticated_user_not_redirected(self, authenticated_client: httpx.AsyncClient):
        """An authenticated user should not be redirected from protected API endpoints."""
        resp = await authenticated_client.get("/api/products/")
        assert resp.status_code != 302

    async def test_auth_me_authenticated(self, authenticated_client: httpx.AsyncClient):
        """/auth/me should return user info when authenticated."""
        resp = await authenticated_client.get("/auth/me")
        assert resp.status_code != 302
        data = resp.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == "test@example.com"


class TestAuthMiddlewareAdvanced:
    async def test_landing_page_is_public(self, client: httpx.AsyncClient):
        """The root / page should be accessible without auth."""
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code != 302

    async def test_health_endpoints_public(self, client: httpx.AsyncClient):
        for path in ["/health", "/health/live", "/health/ready"]:
            resp = await client.get(path)
        assert resp.status_code != 302

    async def test_api_docs_path_not_redirected(self, client: httpx.AsyncClient):
        resp = await client.get("/api/docs", follow_redirects=False)
        assert resp.status_code != 302

    async def test_static_paths_public(self, client: httpx.AsyncClient):
        resp = await client.get("/static/nonexistent.js", follow_redirects=False)
        assert resp.status_code != 302

    async def test_products_api_requires_auth(self, client: httpx.AsyncClient):
        resp = await client.get("/api/products/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_products_page_requires_auth(self, client: httpx.AsyncClient):
        resp = await client.get("/products/", follow_redirects=False)
        assert resp.status_code == 302

    async def test_authenticated_can_access_products_api(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/api/products/")
        assert resp.status_code != 302
        assert resp.json() == []

    async def test_authenticated_can_access_dashboard(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code != 302
