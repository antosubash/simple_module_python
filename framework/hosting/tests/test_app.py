"""Tests for app creation, routing, protected pages, security, and migration."""

from __future__ import annotations

from collections import defaultdict

import httpx
from fastapi import FastAPI
from simple_module_hosting.app_builder import _resolve_project_root, create_app
from simple_module_hosting.settings import Settings


class TestCreateApp:
    async def test_returns_fastapi_instance(self, settings: Settings):
        app = create_app(settings)
        assert isinstance(app, FastAPI)

    async def test_app_state_has_registries(self, app: FastAPI):
        assert hasattr(app.state, "menu_registry")
        assert hasattr(app.state, "perm_registry")
        assert hasattr(app.state, "ff_registry")
        assert hasattr(app.state, "event_bus")
        assert hasattr(app.state, "health_registry")
        assert hasattr(app.state, "settings")
        assert hasattr(app.state, "db")


class TestResolveProjectRoot:
    async def test_honours_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        assert _resolve_project_root() == tmp_path

    async def test_empty_env_var_uses_fallback(self, monkeypatch, tmp_path):
        # Empty string is falsy — must fall through to the path walk.
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("SM_PROJECT_ROOT", "")
        assert _resolve_project_root() != tmp_path


class TestRouteRegistration:
    async def test_expected_routes_registered(self, app: FastAPI):
        """All modules should have their routes registered in the app."""
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]

        assert "/health" in route_paths
        assert "/health/live" in route_paths
        assert "/health/ready" in route_paths

        assert "/api/products/" in route_paths
        assert "/api/products/{product_id}" in route_paths

        assert "/auth/login" in route_paths
        assert "/auth/callback" in route_paths
        assert "/auth/logout" in route_paths
        assert "/auth/me" in route_paths

        # Dashboard — mounted at the /dashboard view prefix; the public
        # landing page at "/" is owned by the host and added in host/main.py,
        # which the create_app fixture doesn't run.
        assert "/dashboard/" in route_paths

    async def test_products_api_methods(self, app: FastAPI):
        """Products endpoints should support the correct HTTP methods."""
        routes_by_path: dict[str, set[str]] = defaultdict(set)
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes_by_path[route.path].update(route.methods)  # ty: ignore[invalid-argument-type]

        assert "GET" in routes_by_path.get("/api/products/", set())
        assert "POST" in routes_by_path.get("/api/products/", set())
        assert "GET" in routes_by_path.get("/api/products/{product_id}", set())
        assert "PUT" in routes_by_path.get("/api/products/{product_id}", set())
        assert "DELETE" in routes_by_path.get("/api/products/{product_id}", set())


class TestProtectedPages:
    async def test_dashboard_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_products_page_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/products/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]


class TestSecurityHeaders:
    async def test_security_headers_present(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "SAMEORIGIN"
        assert resp.headers["x-xss-protection"] == "1; mode=block"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


class TestHealthMigrationStatus:
    async def test_health_includes_migration(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        migration = data["migration"]
        assert migration["is_current"] is True
        assert migration["pending_count"] == 0


class TestMigrationCheck:
    async def test_app_state_has_migration_info(self, app: FastAPI):
        """App state should include migration status after startup."""
        migration = app.state.migration
        assert migration["is_current"] is True
        assert migration["pending_count"] == 0
        assert "current_revision" in migration
        assert "head_revision" in migration
