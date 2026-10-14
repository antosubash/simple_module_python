"""Does a request resolve to *any* route of the app? (#473)

``AuthMiddleware`` only gates paths the router would actually serve. A path
nothing matches falls through to the normal 404 instead of bouncing an
anonymous visitor to the sign-in form (and storing it as their post-login
target). Every path that does resolve stays gated exactly as before.

The probe mirrors Starlette/FastAPI dispatch without running a handler:

* any ``Match`` other than ``NONE`` counts — ``PARTIAL`` is an existing path
  under the wrong method (a 405 for a signed-in caller), so it stays gated;
* the ``redirect_slashes`` toggle counts too — ``/admin/users/`` that only
  resolves by redirecting to ``/admin/users`` is gated like its target;
* FastAPI's low-priority (frontend) routes are consulted when present.

It fails closed: any surprise while matching reports "exists", so the worst
case is today's behaviour (a redirect), never an ungated route.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.routing import Match
from starlette.types import Scope

logger = logging.getLogger(__name__)


def _probe(scope: Scope, path: str | None = None) -> dict[str, Any]:
    # A shallow copy without FastAPI's per-request bookkeeping: matching an
    # included router writes into ``scope["fastapi"]``, which must not leak
    # into the real dispatch that follows.
    probe = {k: v for k, v in scope.items() if k != "fastapi"}
    if path is not None:
        probe["path"] = path
    return probe


def _any_match(router: Any, probe: dict[str, Any]) -> bool:
    for route in router.routes:
        match, _ = route.matches(probe)
        if match != Match.NONE:
            return True
    return False


def route_exists(scope: Scope) -> bool:
    """Whether the app's router would serve this request (or redirect it to a route)."""
    try:
        router = scope["app"].router
        if _any_match(router, _probe(scope)):
            return True
        path: str = scope["path"]
        if getattr(router, "redirect_slashes", False) and path != "/":
            toggled = path.rstrip("/") if path.endswith("/") else path + "/"
            if _any_match(router, _probe(scope, toggled)):
                return True
        low_priority = getattr(router, "_match_low_priority", None)
        if low_priority is not None:
            match = low_priority(_probe(scope))[0]
            if match != Match.NONE:
                return True
    except Exception:
        logger.exception("Route probe failed; treating the path as existing")
        return True
    return False


__all__ = ["route_exists"]
