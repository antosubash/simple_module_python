"""``token_guard``: an API token reaches only permission-gated, non-page routes.

Security review M1: the scope cap only constrains a route that asks for a
permission, so a route needing nothing but a signed-in principal accepted any
token. The guard decides per route from its dependency tree, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.token_guard import (
    TokenAllowed,
    page_route,
    route_admits_tokens,
    token_route_guard,
)


@dataclass
class _Principal:
    id: str = "u1"
    roles: list[str] = field(default_factory=lambda: ["user"])
    permissions: list[str] = field(default_factory=list)
    scopes: list[str] | None = None


def _app(principal: _Principal | None, *, public: bool = False) -> FastAPI:
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None
    api = APIRouter(prefix="/api")

    @api.get("/open")
    async def open_route(request: Request) -> dict:
        return {"user": getattr(request.state.user, "id", None)}

    @api.get("/gated", dependencies=[Depends(RequiresPermission("x.view"))])
    async def gated() -> dict:
        return {"ok": True}

    @api.get("/allowed", dependencies=[Depends(TokenAllowed())])
    async def allowed() -> dict:
        return {"ok": True}

    pages = APIRouter(prefix="/pages", dependencies=[Depends(page_route)])

    @pages.get("/gated", dependencies=[Depends(RequiresPermission("x.view"))])
    async def gated_page() -> dict:
        return {"ok": True}

    app.include_router(api)
    app.include_router(pages)

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.user = principal
        request.scope.setdefault("state", {})["auth_public"] = public
        return await call_next(request)

    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


TOKEN = _Principal(roles=["admin"], scopes=["x.view"])


async def test_token_refused_on_a_route_without_a_permission_gate():
    resp = await _get(_app(TOKEN), "/api/open")
    assert resp.status_code == 403


async def test_token_admitted_on_a_permission_gated_route():
    app = _app(_Principal(scopes=["x.view"], permissions=["x.view"]))
    assert (await _get(app, "/api/gated")).status_code == 200


async def test_token_admitted_on_an_explicitly_allowed_route():
    assert (await _get(_app(TOKEN), "/api/allowed")).status_code == 200


async def test_token_refused_on_a_page_even_when_gated():
    app = _app(_Principal(scopes=["x.view"], permissions=["x.view"]))
    assert (await _get(app, "/pages/gated")).status_code == 403


async def test_session_principal_is_never_affected():
    app = _app(_Principal(scopes=None))
    assert (await _get(app, "/api/open")).status_code == 200


async def test_token_on_a_public_route_runs_as_anonymous():
    resp = await _get(_app(TOKEN, public=True), "/api/open")
    assert resp.status_code == 200
    assert resp.json() == {"user": None}


def _route(app: FastAPI, path: str):
    return next(r for r in app.router.routes if getattr(r, "path", "") == path)


def test_inertia_dependency_marks_a_route_as_a_page():
    app = FastAPI()

    @app.get("/p", dependencies=[Depends(RequiresPermission("x.view"))])
    async def page(inertia: InertiaDep) -> None:
        return None

    assert route_admits_tokens(_route(app, "/p")) is False


def test_a_route_with_no_gate_refuses_tokens():
    app = FastAPI()

    @app.get("/n")
    async def nothing() -> None:
        return None

    assert route_admits_tokens(_route(app, "/n")) is False
    assert route_admits_tokens(None) is False


async def test_token_admitted_through_a_nested_sub_dependency_gate():
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None

    async def inner(_: None = Depends(RequiresPermission("x.view"))) -> None:
        return None

    async def outer(_: None = Depends(inner)) -> None:
        return None

    router = APIRouter()

    @router.get("/nested")
    async def nested(_: None = Depends(outer)) -> dict:
        return {"ok": True}

    app.include_router(router)

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.user = _Principal(scopes=["x.view"], permissions=["x.view"])
        return await call_next(request)

    r = await _get(app, "/nested")
    assert r.status_code == 200, r.text
    assert (await _get(app, "/missing")).status_code == 404


def test_websocket_route_with_the_guard_does_not_break():
    from starlette.testclient import TestClient

    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("hi")
        await websocket.close()

    with TestClient(app).websocket_connect("/ws") as sock:
        assert sock.receive_text() == "hi"


async def test_page_marker_on_a_router_survives_nested_include_router():
    """FastAPI keeps a nested include's router dependencies out of the route's tree."""
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None
    sub = APIRouter()

    @sub.get("/x", dependencies=[Depends(RequiresPermission("x.view"))])
    async def x() -> dict:
        return {"ok": True}

    pages = APIRouter(prefix="/pages", dependencies=[Depends(page_route)])
    pages.include_router(sub)
    app.include_router(pages)

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.user = _Principal(scopes=["x.view"], permissions=["x.view"])
        return await call_next(request)

    assert (await _get(app, "/pages/x")).status_code == 403


def test_page_marker_beats_an_explicit_opt_in():
    app = FastAPI()

    @app.get("/p", dependencies=[Depends(page_route), Depends(TokenAllowed())])
    async def p() -> None:
        return None

    assert route_admits_tokens(_route(app, "/p")) is False
