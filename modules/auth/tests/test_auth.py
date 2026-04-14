"""Tests for the Auth module: UserContext, dependencies, middleware, endpoints."""

from __future__ import annotations

import httpx
import pytest
from auth.contracts.schemas import UserContext

# ── UserContext ───────────────────────────────────────────────────────


class TestUserContext:
    async def test_from_keycloak_userinfo_basic(self):
        userinfo = {
            "sub": "user-123",
            "email": "alice@example.com",
            "name": "Alice Smith",
            "realm_access": {"roles": ["user", "editor"]},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.id == "user-123"
        assert ctx.email == "alice@example.com"
        assert ctx.name == "Alice Smith"
        assert ctx.roles == ["user", "editor"]

    async def test_from_keycloak_userinfo_fallback_username(self):
        userinfo = {
            "sub": "user-456",
            "email": "bob@example.com",
            "preferred_username": "bob",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.name == "bob"

    async def test_from_keycloak_userinfo_missing_fields(self):
        userinfo = {}
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.id == ""
        assert ctx.email == ""
        assert ctx.name == ""
        assert ctx.roles == []

    async def test_has_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["admin", "user"])
        assert ctx.has_role("admin") is True
        assert ctx.has_role("superadmin") is False

    async def test_has_any_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["editor"])
        assert ctx.has_any_role(["admin", "editor"]) is True
        assert ctx.has_any_role(["admin", "superadmin"]) is False


# ── UserContext tenant_id ─────────────────────────────────────────────


class TestUserContextTenantId:
    async def test_tenant_id_from_custom_claim(self):
        """UserContext should read a custom ``tenant_id`` claim from userinfo."""
        userinfo = {
            "sub": "user-123",
            "tenant_id": "acme-corp",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "acme-corp"

    async def test_tenant_id_from_organization_claim(self):
        """UserContext should fall back to Keycloak's organization.id claim."""
        userinfo = {
            "sub": "user-123",
            "organization": {"id": "org-42", "name": "Acme"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "org-42"

    async def test_tenant_id_custom_claim_takes_precedence(self):
        """Custom tenant_id claim should take precedence over organization.id."""
        userinfo = {
            "sub": "user-123",
            "tenant_id": "custom-tenant",
            "organization": {"id": "org-42"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "custom-tenant"

    async def test_tenant_id_missing_is_none(self):
        """When no tenant claim is present, tenant_id should be None."""
        userinfo = {"sub": "user-123"}
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_organization_without_id_is_none(self):
        """An organization claim without an id should leave tenant_id as None."""
        userinfo = {
            "sub": "user-123",
            "organization": {"name": "no-id"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_organization_as_non_dict_is_ignored(self):
        """A non-dict organization claim should not crash; tenant_id stays None."""
        userinfo = {
            "sub": "user-123",
            "organization": "not-a-dict",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_default_is_none(self):
        """Direct construction without tenant_id should default to None."""
        ctx = UserContext(id="1", email="a@b.com", name="A")
        assert ctx.tenant_id is None


# ── Auth dependencies (unit tests) ──────────────────────────────────


class TestGetCurrentUser:
    async def test_raises_401_when_no_user(self):
        """get_current_user raises 401 when request.state has no user."""
        from unittest.mock import MagicMock

        from auth.deps import get_current_user
        from fastapi import HTTPException

        request = MagicMock()
        # Simulate no user on request.state
        del request.state.user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    async def test_returns_user_when_present(self):
        """get_current_user returns the user from request.state."""
        from unittest.mock import MagicMock

        from auth.deps import get_current_user

        user = UserContext(id="u1", email="u@test.com", name="User", roles=["user"])
        request = MagicMock()
        request.state.user = user

        result = await get_current_user(request)
        assert result.id == "u1"


class TestRequirePermission:
    async def test_raises_403_when_missing_permission(self, app):
        """The require_permission check function raises 403 when user lacks permissions."""
        from unittest.mock import MagicMock

        from auth.deps import require_permission
        from fastapi import HTTPException

        # Get the inner check function from the Depends wrapper
        dep = require_permission("products.delete")
        check_fn = dep.dependency

        # Create a mock request with the app's permission registry
        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        # User without the required permission
        user = UserContext(id="u1", email="u@test.com", name="User", roles=["viewer"])

        with pytest.raises(HTTPException) as exc_info:
            await check_fn(request, user)
        assert exc_info.value.status_code == 403

    async def test_admin_bypasses_permission_check(self, app):
        """The require_permission check allows admin users through."""
        from unittest.mock import MagicMock

        from auth.deps import require_permission

        dep = require_permission("products.delete")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        # Admin user should pass without raising
        admin_user = UserContext(id="a1", email="admin@test.com", name="Admin", roles=["admin"])
        await check_fn(request, admin_user)  # Should not raise


# ── AuthMiddleware ───────────────────────────────────────────────────


class TestAuthMiddleware:
    async def test_unauthenticated_request_redirects(self, client: httpx.AsyncClient):
        """Accessing a protected page without a session should redirect to /auth/login."""
        resp = await client.get("/dashboard/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_public_paths_not_redirected(self, client: httpx.AsyncClient):
        """Health and auth paths should be accessible without authentication."""
        resp = await client.get("/health")
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302

    async def test_auth_me_unauthenticated(self, client: httpx.AsyncClient):
        """/auth/me should return authenticated:false when no session."""
        resp = await client.get("/auth/me")
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302
        data = resp.json()
        assert data["authenticated"] is False

    async def test_authenticated_user_not_redirected(self, authenticated_client: httpx.AsyncClient):
        """An authenticated user should not be redirected from protected API endpoints."""
        resp = await authenticated_client.get("/api/products/")
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302

    async def test_auth_me_authenticated(self, authenticated_client: httpx.AsyncClient):
        """/auth/me should return user info when authenticated."""
        resp = await authenticated_client.get("/auth/me")
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302
        data = resp.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == "test@example.com"


# ── UserContext Advanced ─────────────────────────────────────────────


class TestUserContextAdvanced:
    async def test_from_keycloak_with_realm_access_roles(self):
        userinfo = {
            "sub": "u1",
            "name": "Admin",
            "email": "admin@test.com",
            "realm_access": {"roles": ["admin", "user"]},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert "admin" in ctx.roles
        assert "user" in ctx.roles

    async def test_has_any_role_empty_user_roles(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=[])
        assert ctx.has_any_role(["admin"]) is False

    async def test_has_any_role_empty_check_list(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["admin"])
        assert ctx.has_any_role([]) is False

    async def test_has_role_case_sensitive(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["Admin"])
        assert ctx.has_role("admin") is False
        assert ctx.has_role("Admin") is True


# ── Auth Middleware Advanced ─────────────────────────────────────────


class TestAuthMiddlewareAdvanced:
    async def test_landing_page_is_public(self, client: httpx.AsyncClient):
        """The root / page should be accessible without auth."""
        resp = await client.get("/", follow_redirects=False)
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302

    async def test_health_endpoints_public(self, client: httpx.AsyncClient):
        for path in ["/health", "/health/live", "/health/ready"]:
            resp = await client.get(path)
            # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302

    async def test_api_docs_path_not_redirected(self, client: httpx.AsyncClient):
        resp = await client.get("/api/docs", follow_redirects=False)
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302

    async def test_static_paths_public(self, client: httpx.AsyncClient):
        # Static path won't have a file, but shouldn't redirect to login
        resp = await client.get("/static/nonexistent.js", follow_redirects=False)
        # 404 is fine, just not 302 to login
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
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302
        assert resp.json() == []

    async def test_authenticated_can_access_dashboard(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/dashboard", follow_redirects=False)
        # In testing mode docs are disabled (404), but should NOT redirect to login
        assert resp.status_code != 302


# ── Require Permission Advanced ──────────────────────────────────────


class TestRequirePermissionAdvanced:
    async def test_multiple_permissions_any_match(self, app):
        """User with any of the required permissions should pass."""
        from unittest.mock import MagicMock

        from auth.deps import require_permission

        dep = require_permission("products.view", "products.edit")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        # Admin passes regardless
        admin = UserContext(id="a1", email="a@t.com", name="Admin", roles=["admin"])
        await check_fn(request, admin)  # Should not raise

    async def test_non_admin_without_permission_fails(self, app):
        from unittest.mock import MagicMock

        from auth.deps import require_permission
        from fastapi import HTTPException

        dep = require_permission("products.delete")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        user = UserContext(id="u1", email="u@t.com", name="User", roles=["user"])
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(request, user)
        assert exc_info.value.status_code == 403
        assert "products.delete" in str(exc_info.value.detail)


# ── Auth Module Registration ─────────────────────────────────────────


class TestAuthModuleRegistration:
    async def test_auth_module_has_correct_meta(self):
        from auth.module import AuthModule

        mod = AuthModule()
        assert mod.meta.name == "Auth"
        assert mod.meta.route_prefix == "/auth"

    async def test_auth_module_registers_menu_items(self):
        from auth.module import AuthModule

        mod = AuthModule()
        from simple_module_core.menu import MenuRegistry

        reg = MenuRegistry()
        mod.register_menu_items(reg)
        assert len(reg.all_items) == 1
        assert reg.all_items[0].label == "Logout"
        assert reg.all_items[0].url == "/auth/logout"

    async def test_auth_logout_endpoint_exists(self, client: httpx.AsyncClient):
        """The /auth/logout endpoint should exist (even if it redirects)."""
        resp = await client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
