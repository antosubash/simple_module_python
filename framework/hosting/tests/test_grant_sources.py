"""Grant sources reach the door, the menu and the frontend alike (GH #337)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from simple_module_hosting.permissions import RequiresPermission, resolve_principal_permissions


def _registry(*sources) -> PermissionRegistry:
    reg = PermissionRegistry()
    reg.add_group("orders", ["orders.view", "orders.edit"])
    for source in sources:
        reg.add_grant_source(source)
    return reg


def _user(roles: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(id="u1", roles=roles or [])


async def _grants_view(_request, _user):
    return {"orders.view"}


async def _raises(_request, _user):
    raise RuntimeError("database down")


class TestResolvePrincipalPermissions:
    async def test_merges_source_with_roles(self):
        reg = _registry(_grants_view)
        reg.map_role("clerk", ["orders.edit"])
        held = await resolve_principal_permissions(None, _user(["clerk"]), reg)
        assert held == {"orders.view", "orders.edit"}

    async def test_raising_source_fails_closed(self):
        held = await resolve_principal_permissions(None, _user(), _registry(_raises, _grants_view))
        assert held == {"orders.view"}

    async def test_wildcard_skips_sources(self):
        calls: list[str] = []

        async def counting(_request, _user):
            calls.append("called")
            return set()

        held = await resolve_principal_permissions(None, _user(["admin"]), _registry(counting))
        assert "*" in held
        assert calls == []


class TestMiddlewareFoldsSources:
    async def test_frontend_permissions_include_source(self):
        captured: dict = {}

        async def inner_app(scope, receive, send):
            from starlette.requests import Request

            captured["shared"] = Request(scope).state.inertia_shared

        mw = InertiaLayoutDataMiddleware(
            inner_app, menu_registry=MenuRegistry(), permission_registry=_registry(_grants_view)
        )
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "state": {"user": _user()},
            "app": SimpleNamespace(state=SimpleNamespace()),
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_message):
            return None

        await mw(scope, receive, send)
        assert captured["shared"]["auth"]["permissions"] == ["orders.view"]


class TestRequiresPermissionWithoutMiddleware:
    """A bare router has no middleware to resolve first; the door must still await sources."""

    def _app(self, reg: PermissionRegistry) -> FastAPI:
        app = FastAPI()
        app.state.sm = SimpleNamespace(permissions=reg)

        @app.middleware("http")
        async def set_user(request, call_next):
            request.state.user = _user()
            return await call_next(request)

        @app.get("/view", dependencies=[Depends(RequiresPermission("orders.view"))])
        async def view():
            return {"ok": True}

        @app.get("/edit", dependencies=[Depends(RequiresPermission("orders.edit"))])
        async def edit():
            return {"ok": True}

        return app

    async def test_source_grant_admits_and_absence_denies(self):
        transport = ASGITransport(app=self._app(_registry(_grants_view)))
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/view")).status_code == 200
            assert (await client.get("/edit")).status_code == 403
