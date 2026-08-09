"""Tests for app creation, routing, protected pages, security, and migration."""

from __future__ import annotations

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
        from simple_module_test import effective_route_paths

        # Only Auth should be loaded; Dashboard routes must be absent.
        restricted = settings.model_copy(update={"modules_enabled": ["Auth"]})
        app = create_app(restricted)
        paths = effective_route_paths(app)
        # Auth is now contracts-only, so it has no routes — only health remains.
        assert not any(p.startswith("/dashboard") for p in paths)

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

    async def test_module_register_public_routes_is_wired(
        self,
        settings: Settings,
        monkeypatch,
    ):
        """register_public_routes() contributions land on app.state.public_routes."""
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting import app_builder

        class FakePublicMod(ModuleBase):
            meta = ModuleMeta(name="FakePublic")

            def register_public_routes(self, registry):
                registry.add_prefix("/api/fakepublic/stac")
                registry.add_regex(r"/api/fakepublic/datasets/[^/]+/tilejson$", methods={"GET"})

        real_discover = app_builder.discover_modules

        def fake_discover(enabled=None, *, strict=False):
            return [*real_discover(enabled=enabled, strict=strict), FakePublicMod()]

        monkeypatch.setattr(app_builder, "discover_modules", fake_discover)

        app = create_app(settings)
        registry = app.state.public_routes
        assert registry is app.state.sm.public_routes
        assert registry.matches("GET", "/api/fakepublic/stac/collections")
        assert registry.matches("GET", "/api/fakepublic/datasets/7/tilejson")
        assert not registry.matches("PATCH", "/api/fakepublic/datasets/7/tilejson")

    async def test_host_public_paths_setting_is_seeded(self, settings: Settings):
        """SM_AUTH_PUBLIC_PATHS prefixes land on the registry as prefix rules."""
        with_paths = settings.model_copy(
            update={"auth_public_paths": ["/api/hostpublic", "/status"]}
        )
        app = create_app(with_paths)
        registry = app.state.public_routes
        assert registry.matches("GET", "/api/hostpublic/anything")
        assert registry.matches("POST", "/status")
        assert not registry.matches("GET", "/api/private")

    async def test_module_public_route_reachable_anonymously(
        self,
        settings: Settings,
        monkeypatch,
    ):
        """End-to-end: an unauthenticated GET to a module-declared public route
        returns 200, while a sibling gated route under the same prefix 401s.

        This is the repro from issue #191 — a read-only anonymous API
        (STAC / OGC) consumed without a session cookie.
        """
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting import app_builder

        class FakeGisMod(ModuleBase):
            meta = ModuleMeta(name="FakeGis", route_prefix="/api/fakegis")

            def register_routes(self, api_router, view_router):
                @api_router.get("/stac")
                async def stac():
                    return {"type": "Catalog"}

                @api_router.get("/secret")
                async def secret():
                    return {"private": True}

            def register_public_routes(self, registry):
                registry.add_prefix("/api/fakegis/stac")

        real_discover = app_builder.discover_modules

        def fake_discover(enabled=None, *, strict=False):
            return [*real_discover(enabled=enabled, strict=strict), FakeGisMod()]

        monkeypatch.setattr(app_builder, "discover_modules", fake_discover)

        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            public = await client.get("/api/fakegis/stac")
            gated = await client.get("/api/fakegis/secret")

        assert public.status_code == 200
        assert public.json() == {"type": "Catalog"}
        assert gated.status_code == 401

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

        # No modules_enabled allowlist: both auth providers are entry points in
        # the dev workspace, and create_app is expected to activate the named
        # one rather than fail the boot on SM020. auth_provider is passed
        # explicitly so an SM_AUTH_PROVIDER in the developer's .env can't
        # decide which provider this asserts on.
        app = create_app(Settings(auth_provider="users"))

        sm = app.state.sm
        assert isinstance(sm, Services)
        assert [m.meta.name for m in sm.modules].count("Keycloak") == 0
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
        from simple_module_test import effective_route_paths

        route_paths = effective_route_paths(app)

        assert "/health" in route_paths
        assert "/health/live" in route_paths
        assert "/health/ready" in route_paths

        # Users module owns login, register, etc. Auth module is contracts-only.
        assert "/users/login" in route_paths

        # Dashboard — mounted at the /dashboard view prefix; the public
        # landing page at "/" is owned by the host and added in host/main.py,
        # which the create_app fixture doesn't run.
        assert "/dashboard/" in route_paths
        # The bare-prefix Inertia alias ("/dashboard" without the slash) is
        # registered with include_in_schema=False, so it isn't enumerable here;
        # TestProtectedPages::test_dashboard_redirects_unauthenticated covers it.


class TestProtectedPages:
    async def test_dashboard_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/users/login" in resp.headers["location"]


class TestSecurityHeaders:
    async def test_security_headers_present(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "SAMEORIGIN"
        assert resp.headers["x-xss-protection"] == "0"
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
