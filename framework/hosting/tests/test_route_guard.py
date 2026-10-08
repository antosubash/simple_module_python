"""guard_included_routers: skip included routers that cannot match the path.

The guard is a pure optimisation, so most of these pin that routing answers
exactly as it did unguarded; the last one pins that it actually skips.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import _IncludedRouter
from simple_module_hosting._route_guard import guard_included_routers
from starlette.responses import PlainTextResponse


def _app() -> tuple[FastAPI, APIRouter]:
    app = FastAPI()
    alpha = APIRouter(prefix="/api/alpha")

    @alpha.get("/items/{item_id}")
    async def item(item_id: int) -> dict:
        return {"item": item_id}

    @alpha.get("/")
    async def alpha_index() -> dict:
        return {"index": "alpha"}

    nested = APIRouter(prefix="/nested")

    @nested.get("/deep")
    async def deep() -> dict:
        return {"deep": True}

    alpha.include_router(nested)

    beta = APIRouter(prefix="/api/beta")

    @beta.get("/ping")
    async def ping() -> dict:
        return {"beta": "pong"}

    app.include_router(alpha)
    app.include_router(beta)
    return app, alpha


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


@pytest.mark.parametrize(
    ("path", "status", "body"),
    [
        ("/api/alpha/items/7", 200, {"item": 7}),
        ("/api/alpha/", 200, {"index": "alpha"}),
        ("/api/alpha/nested/deep", 200, {"deep": True}),
        ("/api/beta/ping", 200, {"beta": "pong"}),
        ("/api/gamma/ping", 404, None),
        ("/api/alpha/items/not-an-int", 422, None),
    ],
)
async def test_routing_is_unchanged(path: str, status: int, body: dict | None) -> None:
    app, _ = _app()
    guard_included_routers(app)
    response = await _get(app, path)
    assert response.status_code == status
    if body is not None:
        assert response.json() == body


async def test_trailing_slash_redirect_still_fires() -> None:
    """``/api/alpha`` lacks the guard's ``/api/alpha/`` prefix; the redirect
    pass retries with the slash added, which the guard lets through."""
    app, _ = _app()
    guard_included_routers(app)
    response = await _get(app, "/api/alpha")
    assert response.status_code == 307
    assert response.headers["location"].endswith("/api/alpha/")


async def test_a_router_mutated_after_guarding_is_not_filtered_stale() -> None:
    """``add_route`` does not apply the router prefix, so the new route sits
    outside the prefix computed at guard time; it must still be reachable."""
    app, alpha = _app()
    guard_included_routers(app)
    assert (await _get(app, "/api/alpha/items/1")).status_code == 200  # guard primed

    async def outside(_request):
        return PlainTextResponse("outside")

    alpha.add_route("/elsewhere", outside)

    response = await _get(app, "/elsewhere")
    assert response.status_code == 200
    assert response.text == "outside"


async def test_guarding_twice_is_a_no_op() -> None:
    app, _ = _app()
    guard_included_routers(app)
    guarded = [r.matches for r in app.router.routes if isinstance(r, _IncludedRouter)]
    guard_included_routers(app)
    assert [r.matches for r in app.router.routes if isinstance(r, _IncludedRouter)] == guarded
    assert (await _get(app, "/api/beta/ping")).status_code == 200


async def test_a_non_matching_router_is_not_descended() -> None:
    app, alpha = _app()
    guard_included_routers(app)
    descended = 0
    alpha_matches = alpha.matches

    def spy(scope):
        nonlocal descended
        descended += 1
        return alpha_matches(scope)

    alpha.matches = spy  # type: ignore[method-assign]
    assert (await _get(app, "/api/beta/ping")).status_code == 200
    assert descended == 0, "the guard let a request for /api/beta into /api/alpha's routes"


async def test_the_app_lifespan_guards_every_top_level_include(app) -> None:
    from simple_module_hosting._route_guard import _PrefixGuard

    included = [r for r in app.router.routes if isinstance(r, _IncludedRouter)]
    assert included
    assert all(isinstance(r.matches, _PrefixGuard) for r in included)
