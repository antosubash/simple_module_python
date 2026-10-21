"""Who may call each ``/api`` route, read off the built app (#534).

Feeds two consumers that must agree: the OpenAPI export (``security`` per
operation) and diagnostic ``SM031`` (an ``/api`` route nobody guarded).

A route is **public** when ``AuthMiddleware`` would let an anonymous caller
through: the public-route registry, the auth provider's legacy public paths, or
the schema URL itself. The middleware sees a concrete request path while a route
only has a template, so each ``{param}`` is replaced by a placeholder segment
and the route counts as public if the registry matches under any placeholder.
A rule that needs a more specific segment (a regex on a slug) can therefore
over- or under-report; the schema is documentation, the middleware stays the
authority.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel

from simple_module_hosting.token_guard import (
    GATE_ALLOW,
    GATE_AUTHENTICATED,
    GATE_PERMISSION,
    dependant_gate_kinds,
)

__all__ = [
    "API_PREFIX",
    "UNGUARDED_ROUTE_CODE",
    "ApiOperation",
    "check_unguarded_api_routes",
    "is_public_operation",
    "iter_api_operations",
]

API_PREFIX = "/api/"
UNGUARDED_ROUTE_CODE = "SM031"
_PARAM = re.compile(r"\{[^}]*\}")
_PLACEHOLDERS = ("x", "0", "00000000-0000-0000-0000-000000000000")
_GUARD_KINDS = frozenset({GATE_PERMISSION, GATE_ALLOW, GATE_AUTHENTICATED})


class ApiOperation(NamedTuple):
    path: str  # templated, as the OpenAPI schema spells it
    methods: frozenset[str]
    gate_kinds: frozenset[str]


def iter_api_operations(app: FastAPI) -> Iterator[ApiOperation]:
    """Each ``/api/`` route with a dependency tree (plain Starlette routes have none)."""
    for ctx in iter_route_contexts(app.routes):
        path = getattr(ctx, "path_format", None) or ctx.path
        dependant = getattr(ctx, "dependant", None)
        if not path or not path.startswith(API_PREFIX) or dependant is None:
            continue
        methods = frozenset(m.upper() for m in (ctx.methods or ()) if m.upper() != "HEAD")
        yield ApiOperation(path, methods, frozenset(dependant_gate_kinds(dependant)))


def _legacy_public(app: FastAPI, path: str) -> bool:
    provider = getattr(getattr(app.state, "auth", None), "auth_provider", None)
    if provider is None:
        return False
    try:
        prefixes, exact = provider.get_public_paths()
    except Exception:
        return False
    return any(path.startswith(p) for p in prefixes) or path in exact


def is_public_operation(app: FastAPI, method: str, path: str) -> bool:
    """Whether an anonymous *method* on the templated *path* is let through."""
    if path == getattr(app.state, "openapi_url", None):
        return True
    registry = getattr(app.state, "public_routes", None)
    for placeholder in _PLACEHOLDERS:
        concrete = _PARAM.sub(placeholder, path)
        if registry is not None and registry.matches(method, concrete):
            return True
        if _legacy_public(app, concrete):
            return True
    return False


def check_unguarded_api_routes(app: FastAPI) -> list[Diagnostic]:
    """SM031: an ``/api`` route with no permission/allow/authenticated gate and not public."""
    found: list[Diagnostic] = []
    for op in iter_api_operations(app):
        if op.gate_kinds & _GUARD_KINDS:
            continue
        for method in sorted(op.methods):
            if is_public_operation(app, method, op.path):
                continue
            found.append(_unguarded(method, op.path))
    return found


def _unguarded(method: str, path: str) -> Diagnostic:
    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code=UNGUARDED_ROUTE_CODE,
        message=(
            f"{method} {path} has no permission, allow or authenticated gate and is not "
            "a public route; any signed-in user can call it and the OpenAPI schema says nothing "
            "about why"
        ),
        module_name="Hosting",
        suggestion=(
            "Add Depends(RequiresPermission(...)), or Depends(Authenticated()) when any "
            "signed-in user may call it, or register it in register_public_routes"
        ),
    )
