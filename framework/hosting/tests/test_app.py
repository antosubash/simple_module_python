"""Tests for app creation, routing, and overall integration."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from simple_module_db import current_tenant_id
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.middleware import TenantMiddleware
from simple_module_hosting.settings import Settings

# ── App creation ─────────────────────────────────────────────────────


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

    async def test_modules_enabled_limits_loaded_modules(self, settings: Settings):
        """Host respects settings.modules_enabled — only listed modules contribute routes."""
        # Only Auth should be loaded; Products + Dashboard routes must be absent.
        restricted = settings.model_copy(update={"modules_enabled": ["Auth"]})
        app = create_app(restricted)
        paths: set[str] = {str(r.path) for r in app.routes if hasattr(r, "path")}
        assert "/auth/login" in paths
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

        # Monkey-patch discovery to return our fake module alongside the real ones.
        real_discover = app_builder.discover_modules

        def fake_discover(enabled=None):
            return [*real_discover(enabled=enabled), FakeStaticMod()]

        monkeypatch.setattr(app_builder, "discover_modules", fake_discover)

        app = create_app(settings)
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/modules/fakestatic/static" in paths


# ── Frontend module manifest (Gap 2a) ────────────────────────────────


class TestModulePagesManifest:
    async def test_compute_returns_existing_page_dirs(self):
        """Returns {ModuleName: Path} for installed modules that ship a pages/ dir."""
        from simple_module_core import discover_modules
        from simple_module_hosting.scaffolding import compute_module_pages

        modules = discover_modules()
        result = compute_module_pages(modules)

        # Products + Dashboard ship pages/; Auth is API-only (no frontend pages).
        assert {"Products", "Dashboard"}.issubset(result.keys())
        assert "Auth" not in result
        for name, path in result.items():
            assert path.is_dir(), f"{name} -> {path} should exist"
            assert path.name == "pages"

    async def test_compute_skips_modules_without_pages_dir(self, tmp_path, monkeypatch):
        """A module whose package has no pages/ dir is omitted (not an error)."""
        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting.scaffolding import compute_module_pages

        class HeadlessMod(ModuleBase):
            # Its __module__ is tests' package, which has no pages/ dir.
            meta = ModuleMeta(name="Headless")

        result = compute_module_pages([HeadlessMod()])
        assert "Headless" not in result

    async def test_write_manifest_emits_json_and_ts(self, tmp_path):
        """write_module_pages_manifest emits both the JSON manifest and the TS glob file."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.scaffolding import write_module_pages_manifest

        modules = discover_modules()
        written = write_module_pages_manifest(modules, tmp_path)

        manifest = tmp_path / "modules.manifest.json"
        generated = tmp_path / "modules.generated.ts"
        assert manifest.is_file()
        assert generated.is_file()
        assert written == {"manifest": manifest, "generated": generated}

        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "Products" in data
        assert data["Products"].endswith("pages") or data["Products"].endswith("pages/")

        ts = generated.read_text(encoding="utf-8")
        # Should contain an import.meta.glob call per discovered module with pages.
        assert "import.meta.glob" in ts
        assert "Products" in ts
        # And a header marking it auto-generated so devs don't hand-edit.
        assert "AUTO-GENERATED" in ts or "auto-generated" in ts.lower()


# ── Host scaffold (Gap 6) ────────────────────────────────────────────


class TestCreateHost:
    async def test_creates_expected_backend_files(self, tmp_path):
        """create_host writes the full backend + frontend scaffold."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo-host", modules=["Products", "Auth"])

        for relpath in [
            # Backend
            "pyproject.toml",
            "main.py",
            "alembic.ini",
            "migrations/env.py",
            "migrations/script.py.mako",
            "migrations/versions/.gitkeep",
            ".env.example",
            ".gitignore",
            "README.md",
            "Makefile",
            # Frontend
            "client_app/package.json",
            "client_app/tsconfig.json",
            "client_app/vite.config.ts",
            "client_app/main.tsx",
            "client_app/app.tsx",
            "client_app/pages.ts",
            "client_app/styles.css",
            "client_app/pages/Error.tsx",
            "templates/index.html",
        ]:
            assert (dest / relpath).exists(), f"missing: {relpath}"

    async def test_package_json_carries_host_name(self, tmp_path):
        """client_app/package.json has its `name` prefixed with the host name."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-host", modules=[])
        pkg = (dest / "client_app" / "package.json").read_text(encoding="utf-8")
        assert '"name": "my-host-client-app"' in pkg

    async def test_substitutes_host_name_into_pyproject(self, tmp_path):
        """The host name lands in pyproject.toml's [project].name field."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="my-acme-app", modules=[])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "my-acme-app"' in pyproject

    async def test_declares_selected_module_deps(self, tmp_path):
        """Each module from --with appears as a PyPI dep in pyproject.toml."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=["Products", "Auth"])
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        # Module names get converted to PyPI names: simple-module-<lower>.
        assert "simple-module-products" in pyproject
        assert "simple-module-auth" in pyproject

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_host aborts if the destination exists and is non-empty — no clobbering."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "existing"
        dest.mkdir()
        (dest / "unrelated.txt").write_text("do not delete me", encoding="utf-8")

        with pytest.raises(FileExistsError):
            create_host(dest, name="demo", modules=[])

    async def test_env_py_uses_shared_helper(self, tmp_path):
        """Scaffolded migrations/env.py delegates to the shared helper, not inline logic."""
        from simple_module_hosting.scaffolding import create_host

        dest = tmp_path / "demo"
        create_host(dest, name="demo", modules=[])
        env_py = (dest / "migrations" / "env.py").read_text(encoding="utf-8")
        assert "build_module_metadata" in env_py
        assert "make_include_object" in env_py
        # Must NOT embed the old inline loop — that's the refactor we locked in at Gap 1.
        assert "for mod in modules:" not in env_py

    async def test_cli_create_host_runs_end_to_end(self, tmp_path):
        """The Click `sm create-host` command produces a working scaffold."""
        from click.testing import CliRunner
        from simple_module_hosting.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["create-host", "smoke-host", "--dest", str(tmp_path / "out"), "--with", "Products"],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out" / "main.py").is_file()
        assert (tmp_path / "out" / "pyproject.toml").is_file()
        assert "simple-module-products" in (tmp_path / "out" / "pyproject.toml").read_text(
            encoding="utf-8"
        )


class TestCreateModule:
    async def test_creates_expected_module_files(self, tmp_path):
        """create_module writes a PyPI-ready module package."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        for relpath in [
            "pyproject.toml",
            "my_feature/__init__.py",
            "my_feature/module.py",
            "my_feature/endpoints/__init__.py",
            "my_feature/endpoints/api.py",
            "tests/__init__.py",
            "tests/test_module.py",
            ".gitignore",
            "README.md",
        ]:
            assert (dest / relpath).is_file(), f"missing: {relpath}"

    async def test_pyproject_declares_entry_point_and_deps(self, tmp_path):
        """pyproject.toml sets the entry_point and pins the framework API range."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

        assert 'name = "simple-module-my-feature"' in pyproject
        assert "[project.entry-points.simple_module]" in pyproject
        assert "my_feature = " in pyproject  # entry-point key
        assert "simple-module-core" in pyproject

    async def test_module_py_subclasses_module_base(self, tmp_path):
        """The generated module.py has a ModuleBase subclass with the right Meta."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")
        module_py = (dest / "my_feature" / "module.py").read_text(encoding="utf-8")

        assert "class MyFeatureModule(ModuleBase)" in module_py
        assert 'name="MyFeature"' in module_py
        assert "requires_framework=" in module_py

    async def test_snake_case_derivation(self, tmp_path):
        """Module names with dashes, spaces, or camel case convert to snake_case packages."""
        from simple_module_hosting.scaffolding import create_module

        # Caller supplies a PascalCase-ish name; package dir is snake_case.
        dest = tmp_path / "simple-module-order-tracker"
        create_module(dest, name="OrderTracker")
        assert (dest / "order_tracker" / "module.py").is_file()

    async def test_refuses_existing_non_empty_dir(self, tmp_path):
        """create_module aborts rather than clobber an existing directory."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "existing"
        dest.mkdir()
        (dest / "sentinel").write_text("keep me", encoding="utf-8")
        with pytest.raises(FileExistsError):
            create_module(dest, name="MyFeature")

    async def test_cli_create_module_runs_end_to_end(self, tmp_path):
        """The Click `sm create-module` command produces a working scaffold."""
        from click.testing import CliRunner
        from simple_module_hosting.cli import main

        runner = CliRunner()
        dest = tmp_path / "simple-module-smoke"
        result = runner.invoke(
            main,
            ["create-module", "Smoke", "--dest", str(dest)],
        )
        assert result.exit_code == 0, result.output
        assert (dest / "smoke" / "module.py").is_file()
        assert "class SmokeModule(ModuleBase)" in (dest / "smoke" / "module.py").read_text(
            encoding="utf-8"
        )

    async def test_scaffold_ships_github_workflows(self, tmp_path):
        """Gap 8: scaffolded modules include publish.yml + ci.yml."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")

        publish = dest / ".github" / "workflows" / "publish.yml"
        ci = dest / ".github" / "workflows" / "ci.yml"
        assert publish.is_file(), "publish.yml missing"
        assert ci.is_file(), "ci.yml missing"

    async def test_publish_workflow_uses_trusted_publishing(self, tmp_path):
        """publish.yml must request OIDC token and use pypa/gh-action-pypi-publish."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        publish = (dest / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

        # Trusted publishing requires these two knobs — without them the
        # workflow falls back to API-token auth, which defeats the point.
        assert "id-token: write" in publish
        assert "pypa/gh-action-pypi-publish" in publish
        # Should NOT pin a PyPI API token env var — that's the old way.
        assert "PYPI_API_TOKEN" not in publish

    async def test_publish_workflow_triggers_on_version_tag(self, tmp_path):
        """publish.yml fires only on tag push, not every commit to main."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        publish = (dest / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        assert "tags:" in publish

    async def test_workflows_parse_as_valid_yaml(self, tmp_path):
        """Both workflow files must be parseable YAML — catches template substitution bugs."""
        import yaml  # PyYAML ships transitively via uvicorn[standard]
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")

        for wf in ("publish.yml", "ci.yml"):
            path = dest / ".github" / "workflows" / wf
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert isinstance(parsed, dict), f"{wf} did not parse to a mapping"
            assert "jobs" in parsed, f"{wf} has no jobs: key"

    async def test_scaffold_has_pages_dir(self, tmp_path):
        """Gap 2b: modules intended to ship TSX pages get a pages/ dir from day one."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        pages_dir = dest / "widget" / "pages"
        assert pages_dir.is_dir()
        # A .gitkeep avoids an empty dir getting lost during git operations.
        assert (pages_dir / ".gitkeep").is_file()

    async def test_pyproject_force_includes_static_dist(self, tmp_path):
        """Gap 2b: pyproject.toml must ship <pkg>/static/dist/ inside the wheel."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

        # The built JS is normally gitignored, but hatch needs an explicit
        # directive to copy it into the wheel at build time.
        assert "force-include" in pyproject
        assert "widget/static/dist" in pyproject

    async def test_module_py_mounts_static_dist_conditionally(self, tmp_path):
        """Generated module.py exposes static_mounts() that tolerates a missing dist/."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        module_py = (dest / "widget" / "module.py").read_text(encoding="utf-8")

        assert "static_mounts" in module_py
        # The URL prefix must match the host's convention (Gap 5's docstring).
        assert "/modules/widget/static" in module_py

    async def test_gitignore_excludes_built_assets(self, tmp_path):
        """Built JS lives in source control's blind spot; only wheels carry it."""
        from simple_module_hosting.scaffolding import create_module

        dest = tmp_path / "simple-module-widget"
        create_module(dest, name="Widget")
        gitignore = (dest / ".gitignore").read_text(encoding="utf-8")
        assert "static/dist" in gitignore


# ── Health endpoints ─────────────────────────────────────────────────


class TestHealthEndpoints:
    async def test_health(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_health_live(self, client: httpx.AsyncClient):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_health_ready(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data


# ── Route registration ───────────────────────────────────────────────


class TestRouteRegistration:
    async def test_expected_routes_registered(self, app: FastAPI):
        """All modules should have their routes registered in the app."""
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]

        # Health
        assert "/health" in route_paths
        assert "/health/live" in route_paths
        assert "/health/ready" in route_paths

        # Products API
        assert "/api/products/" in route_paths
        assert "/api/products/{product_id}" in route_paths

        # Auth
        assert "/auth/login" in route_paths
        assert "/auth/callback" in route_paths
        assert "/auth/logout" in route_paths
        assert "/auth/me" in route_paths

        # Dashboard
        assert "/dashboard" in route_paths

    async def test_products_api_methods(self, app: FastAPI):
        """Products endpoints should support the correct HTTP methods."""
        from collections import defaultdict

        routes_by_path: dict[str, set[str]] = defaultdict(set)
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes_by_path[route.path].update(route.methods)  # ty: ignore[invalid-argument-type]

        assert "GET" in routes_by_path.get("/api/products/", set())
        assert "POST" in routes_by_path.get("/api/products/", set())
        assert "GET" in routes_by_path.get("/api/products/{product_id}", set())
        assert "PUT" in routes_by_path.get("/api/products/{product_id}", set())
        assert "DELETE" in routes_by_path.get("/api/products/{product_id}", set())


# ── Unauthenticated access to protected pages ───────────────────────


class TestProtectedPages:
    async def test_dashboard_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_products_page_redirects_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/products/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]


# ── Security headers ─────────────────────────────────────────────────


class TestSecurityHeaders:
    async def test_security_headers_present(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "SAMEORIGIN"
        assert resp.headers["x-xss-protection"] == "1; mode=block"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


class TestHealthReady:
    async def test_ready_includes_module_checks(self, app: FastAPI, client: httpx.AsyncClient):
        """If modules registered health checks, /health/ready should include them."""
        from simple_module_core.health import (
            HealthCheck,
            HealthCheckResult,
            HealthRegistry,
            HealthStatus,
        )

        registry: HealthRegistry = app.state.health_registry

        async def check_test_service() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        registry.add(HealthCheck(name="test_service", check=check_test_service))

        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert data["checks"]["test_service"]["status"] == "healthy"

    async def test_ready_degraded_status(self, app: FastAPI, client: httpx.AsyncClient):
        from simple_module_core.health import (
            HealthCheck,
            HealthCheckResult,
            HealthRegistry,
            HealthStatus,
        )

        registry: HealthRegistry = app.state.health_registry

        async def check_degraded() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        registry.add(HealthCheck(name="slow_service", check=check_degraded))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["slow_service"]["detail"] == "slow"

    async def test_ready_unhealthy_on_exception(self, app: FastAPI, client: httpx.AsyncClient):
        from simple_module_core.health import HealthCheck, HealthRegistry

        registry: HealthRegistry = app.state.health_registry

        async def check_broken():
            raise ConnectionError("connection refused")

        registry.add(HealthCheck(name="broken_service", check=check_broken))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["broken_service"]["status"] == "unhealthy"
        assert "connection refused" in data["checks"]["broken_service"]["detail"]

    async def test_ready_no_checks_is_healthy(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"] == {}


# ── Migration check ─────────────────────────────────────────────────


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


# ── TenantMiddleware ─────────────────────────────────────────────────


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "state": {},
    }


async def _noop_receive():  # pragma: no cover - receive is unused in these tests
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(message):  # pragma: no cover - nothing inspects responses
    return None


class TestTenantMiddleware:
    """Unit tests exercising the raw-ASGI TenantMiddleware directly."""

    async def test_skips_non_http_scopes(self):
        """Lifespan / websocket scopes should pass through unchanged."""
        calls = {"count": 0}

        async def inner_app(scope, receive, send):
            calls["count"] += 1
            assert current_tenant_id.get() is None

        mw = TenantMiddleware(inner_app)
        await mw({"type": "lifespan"}, _noop_receive, _noop_send)
        assert calls["count"] == 1

    async def test_tenant_from_user_state_sets_context(self):
        """If request.state.user.tenant_id is set, it becomes the current tenant."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()
            captured["state_tenant_id"] = scope["state"].get("tenant_id")

        scope = _http_scope()
        scope["state"]["user"] = SimpleNamespace(tenant_id="acme-corp")

        await TenantMiddleware(inner_app)(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "acme-corp"
        assert captured["state_tenant_id"] == "acme-corp"

    async def test_tenant_from_header_fallback(self):
        """With no authenticated user, the X-Tenant-ID header should be used."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        await TenantMiddleware(inner_app)(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "header-tenant"

    async def test_user_tenant_id_takes_precedence_over_header(self):
        """Authenticated user's tenant_id must win over the X-Tenant-ID header."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        scope["state"]["user"] = SimpleNamespace(tenant_id="user-tenant")

        await TenantMiddleware(inner_app)(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "user-tenant"

    async def test_no_tenant_leaves_context_unset(self):
        """No user tenant + no header means context stays None and state is None."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()
            captured["state_tenant_id"] = scope["state"].get("tenant_id")

        await TenantMiddleware(inner_app)(_http_scope(), _noop_receive, _noop_send)

        assert captured["tenant_id"] is None
        assert captured["state_tenant_id"] is None

    async def test_context_reset_after_request(self):
        """ContextVar must be reset after the inner app returns, even on error."""

        async def failing_app(scope, receive, send):
            raise RuntimeError("boom")

        scope = _http_scope()
        scope["state"]["user"] = SimpleNamespace(tenant_id="leaked")

        with pytest.raises(RuntimeError, match="boom"):
            await TenantMiddleware(failing_app)(scope, _noop_receive, _noop_send)

        assert current_tenant_id.get() is None

    async def test_user_without_tenant_id_falls_back_to_header(self):
        """An authenticated user whose tenant_id is None shouldn't block header fallback."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"from-header")])
        scope["state"]["user"] = SimpleNamespace(tenant_id=None)

        await TenantMiddleware(inner_app)(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "from-header"


class TestTenantMiddlewareIntegration:
    async def test_app_pipeline_includes_tenant_middleware(self, app: FastAPI):
        """TenantMiddleware should be registered on the FastAPI app's middleware stack."""
        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantMiddleware in middleware_classes
