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
* :class:`TokenAllowed` on a route admits tokens explicitly, for a route that
  is safe for any token without naming a permission.
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

from fastapi import HTTPException, Request
from simple_module_db.listeners import current_user_id

TOKEN_GATE_ATTR = "__sm_token_gate__"
"""Attribute a dependency callable carries to tell the guard what it is."""

GATE_PERMISSION = "permission"
"""A permission check: admits tokens, which it caps at their scopes."""

GATE_ALLOW = "allow"
"""An explicit opt-in: tokens may reach this route without a permission."""

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


async def page_route() -> None:
    """Dependency marker for a page route (added to every module view router)."""


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
    if GATE_ALLOW in kinds:
        admits = True
    elif GATE_PAGE in kinds:
        admits = False
    else:
        admits = GATE_PERMISSION in kinds
    with contextlib.suppress(AttributeError, TypeError):  # a slotted/frozen route
        setattr(route, _POLICY_ATTR, admits)
    return admits


def is_token_principal(user: Any) -> bool:
    """A scoped principal — an API token — as opposed to a session or IdP bearer."""
    return user is not None and getattr(user, "scopes", None) is not None


def _translate(request: Request, key: str, fallback: str) -> str:
    sm = getattr(request.app.state, "sm", None)
    registry = getattr(sm, "i18n_registry", None)
    if registry is None:
        return fallback
    from simple_module_core.i18n import Translator

    default = sm.settings.i18n_default_locale
    locale = getattr(request.state, "locale", default)
    return Translator(registry, locale=locale, default_locale=default).t(key)


async def token_route_guard(request: Request) -> None:
    """App-wide dependency enforcing the rule in this module's docstring."""
    user = getattr(request.state, "user", None)
    if not is_token_principal(user):
        return
    if route_admits_tokens(request.scope.get("route")):
        return
    if (request.scope.get("state") or {}).get("auth_public"):
        # A public route: serve the token holder as the anonymous visitor
        # anyone may be, never as the account behind the token.
        request.state.user = None
        request.state.resolved_permissions = set()
        current_user_id.set(None)
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
    "GATE_PAGE",
    "GATE_PERMISSION",
    "TOKEN_GATE_ATTR",
    "TokenAllowed",
    "is_token_principal",
    "mark_token_gate",
    "page_route",
    "route_admits_tokens",
    "token_route_guard",
]
