"""Tests for TenantMiddleware: user/header sources, context lifecycle, opt-in."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_db import current_tenant_id
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.middleware import TenantMiddleware
from simple_module_hosting.settings import Settings


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
        """With no authenticated user, the configured header should be used."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        await TenantMiddleware(inner_app, header="X-Tenant-ID")(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "header-tenant"

    async def test_header_ignored_when_header_is_none(self):
        """``header=None`` disables the header source entirely."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        await TenantMiddleware(inner_app)(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] is None

    async def test_user_tenant_id_takes_precedence_over_header(self):
        """Authenticated user's tenant_id must win over the X-Tenant-ID header."""
        captured: dict = {}

        async def inner_app(scope, receive, send):
            captured["tenant_id"] = current_tenant_id.get()

        scope = _http_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        scope["state"]["user"] = SimpleNamespace(tenant_id="user-tenant")

        await TenantMiddleware(inner_app, header="X-Tenant-ID")(scope, _noop_receive, _noop_send)

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

        await TenantMiddleware(inner_app, header="X-Tenant-ID")(scope, _noop_receive, _noop_send)

        assert captured["tenant_id"] == "from-header"


class TestTenantMiddlewareIntegration:
    async def test_app_pipeline_includes_tenant_middleware(self, app: FastAPI):
        """TenantMiddleware should be registered when multi_tenant=True (fixture default)."""
        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantMiddleware in middleware_classes

    async def test_tenant_middleware_absent_when_opted_out(self):
        """With ``multi_tenant=False`` the middleware must not be installed."""
        single_tenant_settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
        )
        app = create_app(single_tenant_settings)
        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantMiddleware not in middleware_classes
