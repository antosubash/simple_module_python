"""Per-request menu providers through InertiaLayoutDataMiddleware (GH #340)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from fastapi import FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def _build(menu: MenuRegistry) -> TestClient:
    app = FastAPI()

    @app.get("/shared")
    def shared(request: Request) -> JSONResponse:
        return JSONResponse(request.state.inertia_shared["menus"])

    app.add_middleware(
        InertiaLayoutDataMiddleware, menu_registry=menu, permission_registry=PermissionRegistry()
    )

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        role = request.headers.get("x-role")
        if role:
            request.state.user = SimpleNamespace(roles=[role])
        request.state.tenant_id = request.headers.get("x-tenant", "")
        return await call_next(request)

    app.add_middleware(SessionMiddleware, secret_key="s")
    return TestClient(app)


def _labels(body: dict, section: str = "sidebar") -> list[str]:
    return [i["label"] for i in body[section]]


def test_async_provider_sees_tenant_and_is_per_request() -> None:
    menu = MenuRegistry()
    menu.add(MenuItem(label="Static", url="/s", order=10))

    async def provider(request: Request) -> list[MenuItem]:
        return [MenuItem(label=f"T-{request.state.tenant_id}", url="/t", order=5)]

    menu.add_provider(provider)
    client = _build(menu)
    a = client.get("/shared", headers={"x-role": "user", "x-tenant": "a"}).json()
    b = client.get("/shared", headers={"x-role": "user", "x-tenant": "b"}).json()
    assert _labels(a) == ["T-a", "Static"]  # merged and sorted by order
    assert _labels(b) == ["T-b", "Static"]


def test_sync_provider_and_role_filtering() -> None:
    menu = MenuRegistry()
    menu.add_provider(
        lambda _r: [MenuItem(label="Admins", url="/a", roles=["admin"]), MenuItem("All", "/x")]
    )
    client = _build(menu)
    assert _labels(client.get("/shared", headers={"x-role": "user"}).json()) == ["All"]
    assert sorted(_labels(client.get("/shared", headers={"x-role": "admin"}).json())) == [
        "Admins",
        "All",
    ]
    assert _labels(client.get("/shared").json()) == []  # anonymous: requires_auth


def test_failing_provider_is_isolated(caplog) -> None:
    menu = MenuRegistry()
    menu.add(MenuItem(label="Static", url="/s"))

    async def boom(_r: Request) -> list[MenuItem]:
        raise RuntimeError("x")

    menu.add_provider(boom)
    menu.add_provider(lambda _r: [MenuItem(label="Ok", url="/ok", order=-1)])
    with caplog.at_level(logging.ERROR):
        resp = _build(menu).get("/shared", headers={"x-role": "user"})
    assert resp.status_code == 200
    assert _labels(resp.json()) == ["Ok", "Static"]
    assert any("Menu provider" in r.getMessage() for r in caplog.records)


def test_remove_static_items_invalidates_cache() -> None:
    menu = MenuRegistry()
    menu.add_many([MenuItem(label="A", url="/a"), MenuItem(label="B", url="/b")])
    assert [i.label for i in menu.all_items] == ["A", "B"]
    assert menu.remove(lambda i: i.label == "A") == 1
    assert [i.label for i in menu.all_items] == ["B"]
