"""Effective route paths of an app, without resolving its routes.

FastAPI >= 0.140 includes routers lazily: an ``_IncludedRouter`` builds each
route's dependant, signature and pydantic adapters the first time a request
reaches it, which is ~0.5 s for the full module set. Asking it for its
``effective_route_contexts()`` just to read their paths forces all of that at
once, on every app build, for every router.

The path itself is cheap: it is the include context's prefix plus the route's
own path (``include_context.path_for``), with nested includes folded in by
``include_context.combine``, the same two steps FastAPI's own resolution uses.
A route type with any other shape falls back to FastAPI building that one
route's context. ``tests/test_route_paths.py`` checks the result matches the
resolved paths for every router of a real app, so a FastAPI upgrade that
changes how paths compose fails there rather than misrouting.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette import routing

# Private; see tests/test_route_guard_fastapi_contract.py before widening the
# fastapi dependency bound.
try:
    from fastapi.routing import _IncludedRouter
except ImportError:  # pragma: no cover - older FastAPI flattens eagerly
    _IncludedRouter = None

__all__ = ["app_route_paths", "included_route_paths"]

# Types whose effective path is exactly ``include_context.path_for(route)``.
_PREFIXED = (APIRoute, routing.Route, APIWebSocketRoute)


def included_route_paths(included: Any) -> list[str]:
    """Every effective path under one ``_IncludedRouter``, nested includes too."""
    context = included.include_context
    paths: list[str] = []
    for route in included.original_router.routes:
        if _IncludedRouter is not None and isinstance(route, _IncludedRouter):
            child = _IncludedRouter(
                original_router=route.original_router,
                include_context=context.combine(route.include_context),
            )
            paths.extend(included_route_paths(child))
        elif isinstance(route, _PREFIXED):
            paths.append(context.path_for(route))
        else:
            resolved = included._build_effective_context(route)
            if resolved is not None:
                paths.append(_resolved_path(resolved))
    return paths


def app_route_paths(app: FastAPI) -> list[str]:
    """Every path registered on *app*, flattening its included routers."""
    paths: list[str] = []
    for route in app.routes:
        if _IncludedRouter is not None and isinstance(route, _IncludedRouter):
            paths.extend(included_route_paths(route))
        else:
            paths.append(getattr(route, "path", "") or "")
    return paths


def _resolved_path(context: Any) -> str:
    route = context.starlette_route
    return (getattr(route, "path", "") if route is not None else context.path) or ""
