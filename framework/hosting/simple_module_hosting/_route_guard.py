"""Skip whole included routers whose routes cannot match the request path.

FastAPI >= 0.140 keeps every ``include_router`` as a lazy ``_IncludedRouter``
placeholder instead of copying its routes onto the parent. Matching a request
then asks each placeholder in turn, and a placeholder that cannot match still
walks its subtree's route version and regex-tests every route in it. With one
API and one view router per module the app root holds ~35 placeholders, so a
request for a module near the end of the list tested nearly all ~190 routes:
route matching was ~30% of the CPU of a cheap authenticated request.

Every route under a placeholder shares the common prefix of its effective
paths. A request whose path lacks that prefix cannot match any of them —
neither fully nor partially — so the guard answers ``Match.NONE`` without
descending. Anything else is delegated unchanged, so a match still takes
FastAPI's own path.

The prefix is derived from the routes, not from ``APIRouter.prefix``: a route
added with ``add_route`` does not carry its router's prefix. It is recomputed
whenever FastAPI's route version for that router changes, so a router mutated
after the app was built is never filtered against a stale prefix.

Relies on ``fastapi.routing._IncludedRouter``; on a FastAPI without it (which
flattened routes eagerly and needs no guard) this is a no-op.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from starlette._utils import get_route_path
from starlette.routing import Match
from starlette.types import Scope

try:  # private, and absent before FastAPI 0.140
    from fastapi.routing import _IncludedRouter
except ImportError:  # pragma: no cover - older FastAPI flattens eagerly
    _IncludedRouter = None  # type: ignore[assignment,misc]

__all__ = ["guard_included_routers"]


def _effective_paths(included: Any) -> list[str]:
    paths: list[str] = []
    for ctx in included.effective_route_contexts():
        route = ctx.starlette_route
        paths.append((getattr(route, "path", "") if route is not None else ctx.path) or "")
    return paths


def _common_prefix(paths: list[str]) -> str:
    """The literal leading part every path shares — never past a ``{param}``."""
    if not paths:
        return ""
    return os.path.commonprefix(paths).split("{", 1)[0]


class _PrefixGuard:
    """Replacement ``matches`` for one ``_IncludedRouter`` instance."""

    def __init__(self, included: Any) -> None:
        self._included = included
        self._matches = included.matches
        self._version: int | None = None
        self._prefix = ""

    def _current_prefix(self) -> str:
        version = self._included.original_router._get_routes_version()
        if version != self._version:
            self._prefix = _common_prefix(_effective_paths(self._included))
            self._version = version
        return self._prefix

    def __call__(self, scope: Scope) -> tuple[Match, Scope]:
        prefix = self._current_prefix()
        # "/" (or "") is shared by every path, so it would filter nothing.
        if len(prefix) > 1 and not get_route_path(scope).startswith(prefix):
            return Match.NONE, {}
        return self._matches(scope)


def guard_included_routers(app: FastAPI) -> None:
    """Install a prefix guard on each router included directly into ``app``.

    Computing a guard's prefix resolves its router's effective routes, which is
    also what FastAPI does lazily on the first request to reach them — building
    every route's dependant, signature and pydantic adapters. Doing it here
    moves that one-time cost (hundreds of ms for a full module set) from the
    first request after boot into startup.
    """
    if _IncludedRouter is None:
        return
    for route in app.router.routes:
        if isinstance(route, _IncludedRouter) and not isinstance(route.matches, _PrefixGuard):
            guard = _PrefixGuard(route)
            guard._current_prefix()
            route.matches = guard  # type: ignore[method-assign]
