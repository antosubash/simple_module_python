"""Migrating the auth gate must preserve any-of permission and token semantics (#989)."""

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_hosting.permissions import RequiresPermission


@pytest.mark.parametrize(
    ("held", "scopes", "status"),
    [
        (["products.view"], None, 200),
        (["products.edit"], None, 200),
        ([], None, 403),
        (["products.edit"], ["products.view"], 403),
        (["products.edit"], ["products.edit"], 200),
    ],
)
async def test_any_permission_suffices_within_token_scopes(held, scopes, status):
    app = FastAPI()
    registry = PermissionRegistry()
    registry.map_role("editor", held)
    app.state.sm = SimpleNamespace(permissions=registry)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.user = SimpleNamespace(roles=["editor"], scopes=scopes)
        return await call_next(request)

    @app.get("/", dependencies=[Depends(RequiresPermission("products.view", "products.edit"))])
    async def guarded():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        assert (await client.get("/")).status_code == status
