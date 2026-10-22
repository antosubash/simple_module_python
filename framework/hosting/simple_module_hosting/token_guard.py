"""Which routes an API-token principal may reach.

A token (``api_tokens``' personal access tokens and service keys) is a
*scoped* principal: ``scopes`` is a list, and every permission check caps what
it holds at that list. The cap can only constrain a route that asks for a
permission, though — a route that needs nothing but a signed-in principal
(create an organisation, leave one, read your profile) would otherwise accept
any token, whatever it was scoped to.

So the rule is fail-closed and decided per route, from its dependency tree:

* A route whose tree holds a **permission gate** (``RequiresPermission``, the
  auth module's ``require_permission``) admits tokens — the gate, capped at
  the token's scopes, is what decides.
* A **page** route (anything rendering through Inertia, and every route on a
  module's view router) refuses tokens even when gated: tokens are API
  credentials, and a page's props are a second, unscoped read API.
* :class:`TokenAllowed` on a (non-page) route admits tokens explicitly, for a route that
  is safe for any token without naming a permission.
* :class:`Authenticated` ("any signed-in user") is a gate for SM031 and the
  OpenAPI security export, **not** a token opt-in: on its own a token is still
  refused (the route has no permission a scope could name). Pair it with
  :class:`TokenAllowed` when a token may call it too.
* Everything else refuses a token with ``403``. On a route the public-route
  registry exempts, the token is not refused but **ignored**: the request runs
  as the anonymous visitor it could have been anyway.

Installed once as an app-wide dependency by ``create_app``, so it covers every
``APIRoute`` — module routers, host routes and framework routes alike. Gates
mark themselves with :data:`TOKEN_GATE_ATTR` (duck-typed, so the auth
module's ``require_permission`` can mark itself without framework code
importing a module — SM009). An unscoped principal (a browser session, an
identity provider's bearer token) is never affected.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from simple_module_hosting._anonymous import demote_to_anonymous

TOKEN_GATE_ATTR = "__sm_token_gate__"
"""Attribute a dependency callable carries to tell the guard what it is."""

GATE_PERMISSION = "permission"
"""A permission check: admits tokens, which it caps at their scopes."""

GATE_ALLOW = "allow"
"""An explicit opt-in: tokens may reach this route without a permission."""

GATE_AUTHENTICATED = "authenticated"
"""Any signed-in user may call (:class:`Authenticated`). Does *not* admit tokens."""

GATE_PAGE = "page"
"""A page (Inertia) route: tokens are refused even behind a permission."""

_POLICY_ATTR = "_sm_token_policy"


def mark_token_gate[F: Callable[..., Any]](fn: F, kind: str) -> F:
    """Tag *fn* (a dependency callable) as a gate of *kind*; returns *fn*."""
    setattr(fn, TOKEN_GATE_ATTR, kind)
    return fn


class TokenAllowed:
    """Dependency marker: API tokens may call this route without a permission.

    Use it only for a route whose effect is harmless for *any* token of the
    principal's, whatever it was scoped to — the route's own code is then the
    only check. Prefer a ``RequiresPermission`` gate, which a scope can name.

    Usage::

        @router.get("/ping", dependencies=[Depends(TokenAllowed())])
    """

    __sm_token_gate__ = GATE_ALLOW

    async def __call__(self) -> None:
        return None


class Authenticated:
    """Dependency marker: any signed-in user may call this route (no permission).

    Answers ``401`` when there is no principal. It documents the route as
    deliberately open to every signed-in user, which silences diagnostic
    ``SM031`` (an ``/api`` route with no permission, allow or authenticated
    gate). Tokens stay refused unless the route also carries
    :class:`TokenAllowed`.

    Usage::

        @router.get("/me", dependencies=[Depends(Authenticated())])
    """

    __sm_token_gate__ = GATE_AUTHENTICATED

    async def __call__(self, request: HTTPConnection) -> None:
        if getattr(request.state, "user", None) is None:
            raise HTTPException(status_code=401, detail="Authentication required")


async def page_route(request: HTTPConnection) -> None:
    """Dependency for a page route (added to every module view router).

    It carries the page marker for the tree inspection *and* refuses a token
    itself: a router's own ``dependencies`` reach a route inside a nested
    ``include_router`` only as an include-level dependency, which FastAPI
    keeps out of the original route's ``dependant``. The guard reads the
    effective route (:func:`effective_route`) to see it, but that is FastAPI
    internals — so a page also refuses on its own, whatever the inspection saw.
    """
    await _refuse_token(request)


mark_token_gate(page_route, GATE_PAGE)


def _gate_kinds(dependant: Any, out: set[str], seen: set[int]) -> None:
    if id(dependant) in seen:
        return
    seen.add(id(dependant))
    kind = getattr(getattr(dependant, "call", None), TOKEN_GATE_ATTR, None)
    if isinstance(kind, str):
        out.add(kind)
    for sub in getattr(dependant, "dependencies", None) or ():
        _gate_kinds(sub, out, seen)


def dependant_gate_kinds(dependant: Any) -> set[str]:
    """Every gate kind marked anywhere in *dependant*'s tree."""
    kinds: set[str] = set()
    _gate_kinds(dependant, kinds, set())
    return kinds


def route_admits_tokens(route: Any) -> bool:
    """Whether *route* (the matched ``APIRoute``) may serve a token principal.

    Computed from the route's dependency tree and cached on the route object;
    anything unexpected answers ``False`` (refuse).
    """
    cached = getattr(route, _POLICY_ATTR, None)
    if isinstance(cached, bool):
        return cached
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    kinds: set[str] = set()
    _gate_kinds(dependant, kinds, set())
    if GATE_PAGE in kinds:
        admits = False  # a page wins over an explicit opt-in
    elif GATE_ALLOW in kinds:
        admits = True
    else:
        admits = GATE_PERMISSION in kinds
    with contextlib.suppress(AttributeError, TypeError):  # a slotted/frozen route
        setattr(route, _POLICY_ATTR, admits)
    return admits


def is_token_principal(user: Any) -> bool:
    """A scoped principal — an API token — as opposed to a session or IdP bearer."""
    return user is not None and getattr(user, "scopes", None) is not None


def _translate(request: HTTPConnection, key: str, fallback: str) -> str:
    sm = getattr(request.app.state, "sm", None)
    registry = getattr(sm, "i18n_registry", None)
    if registry is None:
        return fallback
    from simple_module_core.i18n import Translator

    default = sm.settings.i18n_default_locale
    locale = getattr(request.state, "locale", default)
    return Translator(registry, locale=locale, default_locale=default).t(key)


def effective_route(scope: Any) -> Any:
    """The route as FastAPI runs it: include-level dependencies included.

    FastAPI (0.143+) puts the *original* ``APIRoute`` in ``scope["route"]``
    but runs the dependant of the per-inclusion context it records under
    ``scope["fastapi"]["effective_route_context"]`` — the one holding
    ``include_router(..., dependencies=[...])``. Read that when it belongs to
    the matched route; otherwise the matched route itself.
    """
    route = scope.get("route")
    fastapi_scope = scope.get("fastapi")
    context = (
        fastapi_scope.get("effective_route_context") if isinstance(fastapi_scope, dict) else None
    )
    if (
        context is not None
        and route is not None
        and getattr(context, "original_route", None) is route
        and getattr(context, "dependant", None) is not None
    ):
        return context
    return route


async def token_route_guard(request: HTTPConnection) -> None:
    """App-wide dependency enforcing the rule in this module's docstring."""
    if not is_token_principal(getattr(request.state, "user", None)):
        return  # the common case: one attribute read, no tree inspection
    if route_admits_tokens(effective_route(request.scope)):
        return
    await _refuse_token(request)


async def _refuse_token(request: HTTPConnection) -> None:
    """Turn a token principal away (403), or demote it to anonymous if public."""
    user = getattr(request.state, "user", None)
    if not is_token_principal(user):
        return
    if (request.scope.get("state") or {}).get("auth_public"):
        # A public route: serve the token holder as the anonymous visitor
        # anyone may be, never as the account behind the token — tenant
        # context included.
        await demote_to_anonymous(request)
        return
    raise HTTPException(
        status_code=403,
        detail=_translate(
            request,
            "hosting.errors.token_not_allowed",
            "API tokens cannot be used on this route.",
        ),
    )


__all__ = [
    "GATE_ALLOW",
    "GATE_AUTHENTICATED",
    "GATE_PAGE",
    "GATE_PERMISSION",
    "TOKEN_GATE_ATTR",
    "Authenticated",
    "TokenAllowed",
    "dependant_gate_kinds",
    "effective_route",
    "is_token_principal",
    "mark_token_gate",
    "page_route",
    "route_admits_tokens",
    "token_route_guard",
]
