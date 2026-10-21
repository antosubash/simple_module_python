"""Upgrade contract for the private APIs used by simple_module_hosting._route_guard."""

import inspect

import fastapi.routing as routing
import starlette._utils as starlette_utils
from fastapi import APIRouter, FastAPI
from starlette.routing import Match

GUARD = "framework/hosting/simple_module_hosting/_route_guard.py"


def _accepts(fn, name, *args):
    message = f"{name} must be callable with {len(args)} positional arguments; update {GUARD}"
    assert callable(fn), message
    try:
        inspect.signature(fn).bind(*args)
    except (TypeError, ValueError) as exc:
        raise AssertionError(message) from exc
    return fn


def test_private_routing_contract():
    included_type = getattr(routing, "_IncludedRouter", None)
    assert inspect.isclass(included_type), (
        f"fastapi.routing._IncludedRouter must be a class; update {GUARD}"
    )
    get_route_path = getattr(starlette_utils, "get_route_path", None)
    scope = {"type": "http", "path": "/api/item", "root_path": "", "method": "GET"}
    get_route_path = _accepts(get_route_path, "starlette._utils.get_route_path(scope)", scope)
    assert get_route_path(scope) == "/api/item", (
        f"get_route_path must return the route path string; update {GUARD}"
    )

    app = FastAPI()
    router = APIRouter()

    @router.get("/api/item")
    async def item():
        return {}

    app.include_router(router)
    included = next(
        (route for route in app.router.routes if isinstance(route, included_type)), None
    )
    assert included is not None, f"include_router must create an _IncludedRouter; update {GUARD}"
    assert getattr(included, "original_router", None) is router, (
        f"_IncludedRouter.original_router must retain the APIRouter; update {GUARD}"
    )
    version = getattr(router, "_get_routes_version", None)
    version = _accepts(version, "original_router._get_routes_version()")
    assert isinstance(version(), int), f"_get_routes_version() must return an int; update {GUARD}"

    contexts = getattr(included, "effective_route_contexts", None)
    contexts = _accepts(contexts, "_IncludedRouter.effective_route_contexts()")
    resolved = list(contexts())
    assert resolved, f"effective_route_contexts() must yield route contexts; update {GUARD}"
    for ctx in resolved:
        assert hasattr(ctx, "starlette_route"), (
            f"route context must expose starlette_route; update {GUARD}"
        )
        assert isinstance(getattr(ctx, "path", None), str), (
            f"route context must expose a string path; update {GUARD}"
        )
        if ctx.starlette_route is not None:
            assert isinstance(getattr(ctx.starlette_route, "path", None), str), (
                f"context.starlette_route must expose a string path; update {GUARD}"
            )

    matches = getattr(included, "matches", None)
    matches = _accepts(matches, "_IncludedRouter.matches(scope)", scope)
    result = matches(scope)
    assert isinstance(result, tuple) and len(result) == 2, (
        f"matches(scope) must return (Match, Scope); update {GUARD}"
    )
    assert isinstance(result[0], Match) and isinstance(result[1], dict), (
        f"matches(scope) must return (Match, Scope); update {GUARD}"
    )

    def replacement(scope):
        return Match.NONE, {}

    try:
        included.matches = replacement
    except (AttributeError, TypeError) as exc:
        raise AssertionError(
            f"_IncludedRouter.matches must allow instance assignment; update {GUARD}"
        ) from exc
    assert included.matches is replacement, (
        f"_IncludedRouter.matches must retain the assigned callable; update {GUARD}"
    )
    assert included.matches(scope) == (Match.NONE, {}), (
        f"assigned matches(scope) must be callable; update {GUARD}"
    )
