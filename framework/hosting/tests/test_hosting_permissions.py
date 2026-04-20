"""Tests for InertiaLayoutDataMiddleware and RequiresPermission with registry role_map."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from simple_module_hosting.permissions import RequiresPermission


def _http_scope(
    roles: list[str] | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
    principal_serializer=None,
) -> dict:
    state = SimpleNamespace()
    if principal_serializer is not None:
        state.principal_serializer = principal_serializer
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "state": {},
        # InertiaLayoutDataMiddleware reads request.app.state.i18n_registry; a
        # stub app with an empty state is enough for the lookup to return None.
        "app": SimpleNamespace(state=state),
    }
    if roles is not None:
        scope["state"]["user"] = SimpleNamespace(
            id="u1",
            name="Test User",
            email="test@example.com",
            roles=roles,
        )
    return scope


async def _noop_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(message):
    return None


class TestInertiaLayoutDataMiddlewareRoleMap:
    """InertiaLayoutDataMiddleware should consult registry.role_map."""

    async def test_user_role_resolves_via_registry(self):
        """A user with role 'user' gets the permission mapped via map_role."""
        reg = PermissionRegistry()
        reg.add_group("users", ["users.self.profile"])
        reg.map_role("user", ["users.self.profile"])

        menu_reg = MenuRegistry()
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            req = Request(scope)
            captured["resolved"] = req.state.resolved_permissions
            captured["shared"] = req.state.inertia_shared

        mw = InertiaLayoutDataMiddleware(inner_app, menu_registry=menu_reg, permission_registry=reg)
        scope = _http_scope(roles=["user"])
        await mw(scope, _noop_receive, _noop_send)

        assert "users.self.profile" in captured["resolved"]
        assert "users.self.profile" in captured["shared"]["auth"]["permissions"]

    async def test_unauthenticated_gets_empty_permissions(self):
        """Unauthenticated requests get no permissions."""
        reg = PermissionRegistry()
        reg.map_role("user", ["users.self.profile"])
        menu_reg = MenuRegistry()
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            req = Request(scope)
            captured["resolved"] = req.state.resolved_permissions
            captured["shared"] = req.state.inertia_shared

        mw = InertiaLayoutDataMiddleware(inner_app, menu_registry=menu_reg, permission_registry=reg)
        scope = _http_scope(roles=None)  # no user
        await mw(scope, _noop_receive, _noop_send)

        assert captured["resolved"] == set()
        assert captured["shared"]["auth"]["permissions"] == []

    async def test_auth_user_is_none_without_serializer(self):
        """Framework does not project user fields itself — defaults to None."""
        reg = PermissionRegistry()
        menu_reg = MenuRegistry()
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            req = Request(scope)
            captured["shared"] = req.state.inertia_shared

        mw = InertiaLayoutDataMiddleware(inner_app, menu_registry=menu_reg, permission_registry=reg)
        await mw(_http_scope(roles=["user"]), _noop_receive, _noop_send)

        assert captured["shared"]["auth"]["user"] is None
        assert captured["shared"]["auth"]["isAuthenticated"] is True

    async def test_auth_user_uses_registered_principal_serializer(self):
        """A module-registered serializer produces the ``auth.user`` projection."""
        reg = PermissionRegistry()
        menu_reg = MenuRegistry()
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            req = Request(scope)
            captured["shared"] = req.state.inertia_shared

        mw = InertiaLayoutDataMiddleware(inner_app, menu_registry=menu_reg, permission_registry=reg)
        scope = _http_scope(
            roles=["user"],
            principal_serializer=lambda u: {"id": u.id, "display": u.name.upper()},
        )
        await mw(scope, _noop_receive, _noop_send)

        assert captured["shared"]["auth"]["user"] == {"id": "u1", "display": "TEST USER"}

    async def test_admin_role_still_gets_all_permissions(self):
        """Admin users still get all permissions via wildcard expansion."""
        reg = PermissionRegistry()
        reg.add_group("products", ["products.view", "products.create"])
        menu_reg = MenuRegistry()
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            req = Request(scope)
            captured["shared"] = req.state.inertia_shared

        mw = InertiaLayoutDataMiddleware(inner_app, menu_registry=menu_reg, permission_registry=reg)
        scope = _http_scope(roles=["admin"])
        await mw(scope, _noop_receive, _noop_send)

        perms = captured["shared"]["auth"]["permissions"]
        assert "products.view" in perms
        assert "products.create" in perms


class TestRequiresPermissionWithRoleMap:
    """RequiresPermission uses registry role_map in middleware and fallback."""

    def _build_app(self, reg: PermissionRegistry, permission: str) -> FastAPI:
        """Build a minimal FastAPI app with the middleware and a protected route."""
        from types import SimpleNamespace

        from simple_module_core.menu import MenuRegistry

        app = FastAPI()
        app.state.sm = SimpleNamespace(permissions=reg)

        menu_reg = MenuRegistry()
        app.add_middleware(
            InertiaLayoutDataMiddleware,
            menu_registry=menu_reg,
            permission_registry=reg,
        )

        @app.get("/protected", dependencies=[Depends(RequiresPermission(permission))])
        async def protected():
            return {"ok": True}

        return app

    def _make_client(self, app: FastAPI, roles: list[str]) -> AsyncClient:
        """Return an async client with a fake authenticated user."""

        async def _set_user(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["user"] = SimpleNamespace(
                    id="u1",
                    name="Test",
                    email="test@example.com",
                    roles=roles,
                )
            await app(scope, receive, send)

        transport = ASGITransport(app=_set_user)  # type: ignore[arg-type]
        return AsyncClient(transport=transport, base_url="http://testserver")

    async def test_role_with_permission_gets_200(self):
        reg = PermissionRegistry()
        reg.add_group("products", ["products.edit"])
        reg.map_role("editor", ["products.edit"])

        app = self._build_app(reg, "products.edit")
        async with self._make_client(app, ["editor"]) as client:
            resp = await client.get("/protected")
        assert resp.status_code == 200

    async def test_role_without_permission_gets_403(self):
        reg = PermissionRegistry()
        reg.add_group("products", ["products.edit"])
        reg.map_role("editor", ["products.edit"])

        app = self._build_app(reg, "products.edit")
        async with self._make_client(app, ["viewer"]) as client:
            resp = await client.get("/protected")
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self):
        reg = PermissionRegistry()
        reg.add_group("products", ["products.edit"])
        reg.map_role("editor", ["products.edit"])

        app = self._build_app(reg, "products.edit")
        # No user in state — use the raw app transport
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/protected")
        assert resp.status_code == 401
