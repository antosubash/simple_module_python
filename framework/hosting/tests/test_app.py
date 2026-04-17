"""Tests for app creation, routing, protected pages, security, and migration."""

from __future__ import annotations

from collections import defaultdict

import httpx
import pytest
from fastapi import FastAPI
from simple_module_hosting.app_builder import _resolve_project_root, create_app
from simple_module_hosting.settings import Settings


class TestCreateApp:
    async def test_returns_fastapi_instance(self, settings: Settings):
        app = create_app(settings)
        assert isinstance(app, FastAPI)

    async def test_app_state_has_registries(self, app: FastAPI):
        # After Task 10, loose keys are removed. Access via app.state.sm.* instead.
        assert hasattr(app.state, "sm")
        sm = app.state.sm
        assert sm.menu_registry is not None
        assert sm.permissions is not None
        assert sm.feature_flags is not None
        assert sm.event_bus is not None
        assert sm.health_registry is not None
        assert sm.settings is not None
        assert sm.db is not None

    async def test_modules_enabled_limits_loaded_modules(self, settings: Settings):
        """Host respects settings.modules_enabled — only listed modules contribute routes."""
        # Only Auth should be loaded; Products + Dashboard routes must be absent.
        restricted = settings.model_copy(update={"modules_enabled": ["Auth"]})
        app = create_app(restricted)
        paths: set[str] = {str(r.path) for r in app.routes if hasattr(r, "path")}
        # Auth is now contracts-only, so it has no routes — only health remains.
        assert not any(p.startswith("/api/products") for p in paths)
        assert "/dashboard" not in paths

    async def test_module_static_mounts_become_app_routes(
        self,
        settings: Settings,
        tmp_path,
        monkeypatch,
    ):
        """Directories returned from ModuleBase.static_mounts() get mounted at boot."""
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting import app_builder

        asset_dir = tmp_path / "module_assets"
        asset_dir.mkdir()
        (asset_dir / "probe.txt").write_text("hello", encoding="utf-8")

        class FakeStaticMod(ModuleBase):
            meta = ModuleMeta(name="FakeStatic")

            def static_mounts(self):
                return {"/modules/fakestatic/static": asset_dir}

        real_discover = app_builder.discover_modules

        def fake_discover(enabled=None, *, strict=False):
            return [*real_discover(enabled=enabled, strict=strict), FakeStaticMod()]

        monkeypatch.setattr(app_builder, "discover_modules", fake_discover)

        app = create_app(settings)
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/modules/fakestatic/static" in paths

    async def test_app_state_has_sm_services(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """create_app populates app.state.sm with a Services instance."""
        from simple_module_core.services import Services

        monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("SM_SECRET_KEY", "x" * 48)
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        (tmp_path / "host" / "templates").mkdir(parents=True)
        (tmp_path / "host" / "templates" / "index.html").write_text("<html></html>")

        app = create_app()

        sm = app.state.sm
        assert isinstance(sm, Services)
        # All registries and state are accessed via app.state.sm.* after Task 10.
        assert sm.settings is not None
        assert sm.db is not None
        assert sm.event_bus is not None
        assert sm.menu_registry is not None
        assert sm.permissions is not None
        assert sm.feature_flags is not None
        assert sm.health_registry is not None
        assert sm.i18n_registry is not None
        assert sm.inertia_config is not None
        assert len(sm.modules) > 0


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

        # Users module owns login, register, etc. Auth module is contracts-only.
        assert "/users/login" in route_paths

        # Dashboard — mounted at the /dashboard view prefix; the public
        # landing page at "/" is owned by the host and added in host/main.py,
        # which the create_app fixture doesn't run.
        assert "/dashboard/" in route_paths

    async def test_products_api_methods(self, app: FastAPI):
        """Products endpoints should support the correct HTTP methods."""
        routes_by_path: dict[str, set[str]] = defaultdict(set)
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes_by_path[route.path].update(route.methods)

        assert "GET" in routes_by_path.get("/api/products/", set())
        assert "POST" in routes_by_path.get("/api/products/", set())
        assert "GET" in routes_by_path.get("/api/products/{product_id}", set())
        assert "PUT" in routes_by_path.get("/api/products/{product_id}", set())
        assert "DELETE" in routes_by_path.get("/api/products/{product_id}", set())


class TestProtectedPages:
    async def test_dashboard_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/users/login" in resp.headers["location"]

    async def test_products_page_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/products/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/users/login" in resp.headers["location"]


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
