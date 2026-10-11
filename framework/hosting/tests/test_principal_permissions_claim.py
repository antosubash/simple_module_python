"""A principal's own ``permissions`` (token/IdP claims) reach the door (GH #436)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.permissions import (
    RequiresPermission,
    resolve_principal_permissions,
    resolved_permissions_for,
)


def _registry() -> PermissionRegistry:
    reg = PermissionRegistry()
    reg.add_group("x", ["x.read", "x.write"])
    return reg


def _user(permissions: list[str] | None = None, roles: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(id="u1", roles=roles or [], permissions=permissions or [])


class TestResolvePrincipalPermissions:
    async def test_user_permissions_are_merged(self):
        held = await resolve_principal_permissions(None, _user(["x.read"]), _registry())
        assert held == {"x.read"}

    async def test_merged_without_a_registry(self):
        held = await resolve_principal_permissions(None, _user(["x.read"]), None)
        assert "x.read" in held

    async def test_merged_with_role_permissions(self):
        reg = _registry()
        reg.map_role("clerk", ["x.write"])
        held = await resolve_principal_permissions(None, _user(["x.read"], ["clerk"]), reg)
        assert held == {"x.read", "x.write"}

    async def test_claimed_wildcard_is_dropped(self):
        held = await resolve_principal_permissions(None, _user(["*", "x.read"]), _registry())
        assert held == {"x.read"}

    async def test_principal_without_attribute(self):
        held = await resolve_principal_permissions(None, SimpleNamespace(roles=[]), _registry())
        assert held == set()


class TestSyncFallbackAgrees:
    def _request(self, user) -> SimpleNamespace:
        app = SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(permissions=_registry())))
        return SimpleNamespace(app=app, state=SimpleNamespace(user=user))

    def test_user_permissions_merged_wildcard_dropped(self):
        held = resolved_permissions_for(self._request(_user(["*", "x.read"])))
        assert held == {"x.read"}


class TestRequiresPermission:
    def _app(self, user) -> FastAPI:
        app = FastAPI()
        app.state.sm = SimpleNamespace(permissions=_registry())

        @app.middleware("http")
        async def set_user(request, call_next):
            request.state.user = user
            return await call_next(request)

        @app.get("/read", dependencies=[Depends(RequiresPermission("x.read"))])
        async def read():
            return {"ok": True}

        @app.get("/write", dependencies=[Depends(RequiresPermission("x.write"))])
        async def write():
            return {"ok": True}

        return app

    async def _status(self, user, path: str) -> int:
        transport = ASGITransport(app=self._app(user))
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            return (await client.get(path)).status_code

    async def test_claimed_permission_admits(self):
        assert await self._status(_user(["x.read"]), "/read") == 200
        assert await self._status(_user(["x.read"]), "/write") == 403

    async def test_claimed_wildcard_is_not_a_wildcard(self):
        assert await self._status(_user(["*"]), "/write") == 403
