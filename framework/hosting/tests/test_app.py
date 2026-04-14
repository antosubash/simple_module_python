"""Tests for app creation, routing, and overall integration."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from simple_module_hosting.app_builder import create_app
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


class TestTenantMiddleware:
    """Unit tests exercising the raw-ASGI TenantMiddleware directly."""

    @staticmethod
    def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
        return {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers or [],
            "state": {},
        }

    @staticmethod
    async def _noop_receive():  # pragma: no cover - receive is unused in these tests
        return {"type": "http.request", "body": b"", "more_body": False}

    @staticmethod
    async def _noop_send(message):  # pragma: no cover - nothing inspects responses
        return None

    async def test_skips_non_http_scopes(self):
        """Lifespan / websocket scopes should pass through unchanged."""
        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        calls = {"count": 0}

        async def inner_app(scope, receive, send):
            calls["count"] += 1
            # ContextVar must not be set for non-http scopes
            assert current_tenant_id.get() is None

        mw = TenantMiddleware(inner_app)
        await mw({"type": "lifespan"}, self._noop_receive, self._noop_send)
        assert calls["count"] == 1

    async def test_tenant_from_user_state_sets_context(self):
        """If request.state.user.tenant_id is set, it becomes the current tenant."""
        from types import SimpleNamespace

        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()
            captured["state_tenant_id"] = scope["state"].get("tenant_id")

        scope = self._http_scope()
        scope["state"]["user"] = SimpleNamespace(tenant_id="acme-corp")

        mw = TenantMiddleware(inner_app)
        await mw(scope, self._noop_receive, self._noop_send)

        assert captured["tenant_id"] == "acme-corp"
        assert captured["state_tenant_id"] == "acme-corp"

    async def test_tenant_from_header_fallback(self):
        """With no authenticated user, the X-Tenant-ID header should be used."""
        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = self._http_scope(headers=[(b"x-tenant-id", b"header-tenant")])

        mw = TenantMiddleware(inner_app)
        await mw(scope, self._noop_receive, self._noop_send)

        assert captured["tenant_id"] == "header-tenant"

    async def test_user_tenant_id_takes_precedence_over_header(self):
        """Authenticated user's tenant_id must win over the X-Tenant-ID header."""
        from types import SimpleNamespace

        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = self._http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        scope["state"]["user"] = SimpleNamespace(tenant_id="user-tenant")

        mw = TenantMiddleware(inner_app)
        await mw(scope, self._noop_receive, self._noop_send)

        assert captured["tenant_id"] == "user-tenant"

    async def test_no_tenant_leaves_context_unset(self):
        """No user tenant + no header means context stays None and state is None."""
        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()
            captured["state_tenant_id"] = scope["state"].get("tenant_id")

        mw = TenantMiddleware(inner_app)
        scope = self._http_scope()
        await mw(scope, self._noop_receive, self._noop_send)

        assert captured["tenant_id"] is None
        assert captured["state_tenant_id"] is None

    async def test_context_reset_after_request(self):
        """ContextVar must be reset after the inner app returns, even on error."""
        from types import SimpleNamespace

        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        async def failing_app(scope, receive, send):
            raise RuntimeError("boom")

        scope = self._http_scope()
        scope["state"]["user"] = SimpleNamespace(tenant_id="leaked")

        mw = TenantMiddleware(failing_app)
        with pytest.raises(RuntimeError, match="boom"):
            await mw(scope, self._noop_receive, self._noop_send)

        # Even after exception, the ContextVar must be back to default
        assert current_tenant_id.get() is None

    async def test_user_without_tenant_id_falls_back_to_header(self):
        """An authenticated user whose tenant_id is None shouldn't block header fallback."""
        from types import SimpleNamespace

        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = self._http_scope(headers=[(b"x-tenant-id", b"from-header")])
        scope["state"]["user"] = SimpleNamespace(tenant_id=None)

        mw = TenantMiddleware(inner_app)
        await mw(scope, self._noop_receive, self._noop_send)

        assert captured["tenant_id"] == "from-header"


# ── TenantMiddleware integration ─────────────────────────────────────


class TestTenantMiddlewareIntegration:
    """Integration tests: tenant is resolved through the full middleware pipeline."""

    async def test_request_state_tenant_id_set_by_header(self, client: httpx.AsyncClient):
        """An unauthenticated public request with X-Tenant-ID should still set state."""
        from simple_module_db import current_tenant_id
        from simple_module_hosting.middleware import TenantMiddleware

        # We can't read request.state from outside, so install a probe middleware
        # that captures it. Instead, exercise the middleware class directly against
        # a realistic scope to confirm the integration.
        captured: dict = {}

        async def inner(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()
            captured["state_tenant_id"] = scope["state"].get("tenant_id")

        mw = TenantMiddleware(inner)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/products/",
            "headers": [(b"x-tenant-id", b"integration-tenant")],
            "state": {},
        }

        async def recv():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            return None

        await mw(scope, recv, send)

        assert captured["tenant_id"] == "integration-tenant"
        assert captured["state_tenant_id"] == "integration-tenant"

    async def test_app_pipeline_includes_tenant_middleware(self, app: FastAPI):
        """TenantMiddleware should be registered on the FastAPI app's middleware stack."""
        from simple_module_hosting.middleware import TenantMiddleware

        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantMiddleware in middleware_classes
