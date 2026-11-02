"""``_route_paths`` gives the paths FastAPI's own resolution would, without resolving."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.routing import _IncludedRouter
from simple_module_hosting._route_paths import app_route_paths, included_route_paths
from starlette.responses import PlainTextResponse


def _resolved(included) -> list[str]:
    paths = []
    for ctx in included.effective_route_contexts():
        route = ctx.starlette_route
        paths.append((getattr(route, "path", "") if route is not None else ctx.path) or "")
    return paths


def _included(app: FastAPI) -> list:
    return [route for route in app.router.routes if isinstance(route, _IncludedRouter)]


def _nested_app() -> FastAPI:
    leaf = APIRouter(prefix="/leaf")

    @leaf.get("/item/{item_id}")
    async def item(item_id: int):
        return {"id": item_id}

    async def plain(request):
        return PlainTextResponse("ok")

    leaf.add_route("/plain", plain)  # a starlette Route: no router prefix applied

    @leaf.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.close()

    middle = APIRouter(prefix="/middle")

    @middle.get("")
    async def bare():
        return {}

    middle.include_router(leaf, prefix="/extra")
    middle.include_router(APIRouter(), prefix="/empty")

    app = FastAPI()
    app.include_router(middle, prefix="/api")
    app.include_router(leaf)

    @app.get("/root")
    async def root():
        return {}

    return app


def test_nested_includes_compose_like_fastapi():
    app = _nested_app()
    for included in _included(app):
        mine = included_route_paths(included)
        assert mine == _resolved(included)
    assert "/api/middle/extra/leaf/item/{item_id}" in app_route_paths(app)


def test_computing_paths_resolves_no_route():
    app = _nested_app()
    for included in _included(app):
        included_route_paths(included)
        assert included._effective_candidates_version is None


async def test_every_router_of_the_real_app_matches(app):
    routers = _included(app)
    assert routers
    for included in routers:
        assert included_route_paths(included) == _resolved(included), included.original_router


def test_the_guard_resolves_routes_only_when_asked_to_warm():
    from simple_module_hosting._route_guard import guard_included_routers

    cold, warm = _nested_app(), _nested_app()
    guard_included_routers(cold, warm=False)
    guard_included_routers(warm)

    assert all(r._effective_candidates_version is None for r in _included(cold))
    assert all(r._effective_candidates_version is not None for r in _included(warm))
