"""Declare which ``/api`` route does what a non-GET view route does.

A page route refuses API tokens (``token_guard``), so anything a browser can
change through a view form must also be reachable through the JSON API, or the
project CLI cannot do it. Every non-GET view route therefore declares either:

* :func:`api_equivalent` — the ``/api`` operation (method and path template, as
  registered) that performs the same change. A view acting on several scopes
  (system and tenant) declares one per scope. A host test resolves each against
  the built app and checks it admits tokens.
* :func:`api_exempt` — why no token may do this at all (logout, sign-in flows,
  the signed-in account's own profile, token management, the setup wizard, the
  locale switch). Use the reason constants below.

Both return a no-op dependency carrying the declaration, used as::

    @router.post(
        "/{item_id}",
        dependencies=[Depends(api_equivalent("PUT", "/api/orders/{item_id}"))],
    )
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

from fastapi.routing import iter_route_contexts
from starlette.routing import Mount, compile_path

from simple_module_hosting.auth.token_guard import dependant_gate_kinds, gate_kinds_admit_tokens

__all__ = [
    "API_DECLARATION_ATTR",
    "EXEMPT_AUTH_FLOW",
    "EXEMPT_LOCALE",
    "EXEMPT_LOGOUT",
    "EXEMPT_SELF_ACCOUNT",
    "EXEMPT_SETUP",
    "EXEMPT_TOKEN_MANAGEMENT",
    "ApiEquivalent",
    "ApiExempt",
    "api_equivalent",
    "api_exempt",
    "dependant_api_declarations",
    "view_route_offenders",
]

API_DECLARATION_ATTR = "__sm_api_declaration__"
"""Attribute the marker dependency carries: an :class:`ApiEquivalent` or :class:`ApiExempt`."""

EXEMPT_LOGOUT = "logout: ends the browser session; a token is revoked instead"
EXEMPT_AUTH_FLOW = "sign-in flow: establishes a browser session, which a token never has"
EXEMPT_SELF_ACCOUNT = "self-account: the signed-in person's own profile, password or sessions"
EXEMPT_TOKEN_MANAGEMENT = "token management: a token may not mint or revoke tokens"
EXEMPT_SETUP = "setup wizard: first-run configuration before any account or token exists"
EXEMPT_LOCALE = "locale switch: a per-session display preference"

_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_API_PREFIX = "/api/"


class ApiEquivalent(NamedTuple):
    method: str
    path: str


class ApiExempt(NamedTuple):
    reason: str


def _marker(declaration: ApiEquivalent | ApiExempt) -> Callable[[], Any]:
    async def declared() -> None:
        return None

    setattr(declared, API_DECLARATION_ATTR, declaration)
    return declared


def api_equivalent(method: str, path: str) -> Callable[[], Any]:
    """Dependency: this view does what ``method path`` (an ``/api`` route) does."""
    verb = method.upper()
    if verb not in _METHODS:
        raise ValueError(f"api_equivalent method must be one of {sorted(_METHODS)}, got {method!r}")
    if not path.startswith(_API_PREFIX):
        raise ValueError(f"api_equivalent path must start with /api/, got {path!r}")
    return _marker(ApiEquivalent(verb, path))


def api_exempt(reason: str) -> Callable[[], Any]:
    """Dependency: no token may do what this view does, for *reason*."""
    if not reason.strip():
        raise ValueError("api_exempt needs a reason")
    return _marker(ApiExempt(reason))


def _collect(dependant: Any, out: list[ApiEquivalent | ApiExempt], seen: set[int]) -> None:
    if id(dependant) in seen:
        return
    seen.add(id(dependant))
    found = getattr(getattr(dependant, "call", None), API_DECLARATION_ATTR, None)
    if isinstance(found, ApiEquivalent | ApiExempt):
        out.append(found)
    for sub in getattr(dependant, "dependencies", None) or ():
        _collect(sub, out, seen)


def dependant_api_declarations(dependant: Any) -> list[ApiEquivalent | ApiExempt]:
    """Every declaration in *dependant*'s tree (include-level dependencies included)."""
    out: list[ApiEquivalent | ApiExempt] = []
    _collect(dependant, out, set())
    return out


class _Walked(NamedTuple):
    path: str  # normalized template (``{param}``), as shown in offender lines
    methods: frozenset[str]
    dependant: Any
    template: str  # as registered, converters kept (``{param:int}``), mount prefix included


def _walk(routes: Any, prefix: str = "") -> Iterator[_Walked]:
    """Each route in dispatch order, as FastAPI runs it, mounted sub-apps included.

    Include-level dependencies come from ``iter_route_contexts``; a ``Mount``
    contributes its path template as a prefix to every route beneath it.
    """
    for route in routes:
        if isinstance(route, Mount):
            yield from _walk(route.routes, prefix + route.path)
            continue
        for ctx in iter_route_contexts([route]):
            template = getattr(ctx, "path", None)
            dependant = getattr(ctx, "dependant", None)
            if not template or dependant is None:
                continue
            methods = frozenset(m.upper() for m in (getattr(ctx, "methods", None) or ()))
            full = prefix + template
            yield _Walked(_normalize(full), methods, dependant, full)


_CONVERTER = re.compile(r"\{(\w+)(?::\w+)?\}")
_SAMPLES = {
    "int": "1",
    "float": "1.0",
    "uuid": "00000000-0000-0000-0000-000000000000",
    "path": "sample/path",
}
_PLACEHOLDER = "_sm_sample_"


def _normalize(template: str) -> str:
    """``/a/{id:int}`` -> ``/a/{id}``: the form a declaration is written in."""
    return _CONVERTER.sub(r"{\1}", template)


def _sample(template: str) -> str:
    """A concrete path the route registered as *template* accepts."""
    return re.sub(
        r"\{\w+(?::(\w+))?\}",
        lambda m: _SAMPLES.get(m.group(1) or "", _PLACEHOLDER),
        template,
    )


class _ApiRoute(NamedTuple):
    path: str
    template: str
    pattern: re.Pattern[str]  # converter-aware, so an int-only route does not shadow a literal
    methods: frozenset[str]
    admits: bool


def _api_routes(app: Any) -> list[_ApiRoute]:
    """Every ``/api`` route in dispatch order, with whether it admits tokens."""
    found: list[_ApiRoute] = []
    for walked in _walk(app.routes):
        if not walked.path.startswith(_API_PREFIX):
            continue
        pattern, _, _ = compile_path(walked.template)
        admits = gate_kinds_admit_tokens(dependant_gate_kinds(walked.dependant))
        found.append(_ApiRoute(walked.path, walked.template, pattern, walked.methods, admits))
    return found


def _resolve(routes: list[_ApiRoute], declared: ApiEquivalent) -> bool | None:
    """Whether the route a request for *declared* reaches admits tokens; ``None`` if none does.

    The declaration must name a registered route exactly (method and normalized path
    template), so a typo cannot pass by matching a ``{param}`` route. Admission is then
    judged on the route that actually dispatches a request to it: the first, in dispatch
    order, whose converter-aware pattern and method match a concrete sample of the target.
    An earlier route (``/api/items/{id}``) can shadow a later literal one
    (``/api/items/special``); an ``{id:int}`` route cannot.
    """
    wanted = _normalize(declared.path)
    target = next(
        (r for r in routes if declared.method in r.methods and r.path == wanted),
        None,
    )
    if target is None:
        return None
    sample = _sample(target.template)
    for route in routes:
        if declared.method in route.methods and route.pattern.match(sample):
            return route.admits
    return target.admits


def _declaration_problem(declarations: list[ApiEquivalent | ApiExempt]) -> str | None:
    exempt = sum(isinstance(d, ApiExempt) for d in declarations)
    equivalent = len(declarations) - exempt
    if exempt and equivalent:
        return "declares both api_exempt and api_equivalent"
    if exempt > 1:
        return f"{exempt} api_exempt declarations, need exactly one"
    if not declarations:
        return "no api_equivalent or api_exempt declaration"
    return None


def view_route_offenders(app: Any) -> list[str]:
    """Every non-GET route outside ``/api/`` whose declaration is missing or wrong.

    A route needs at least one :class:`ApiEquivalent` (one per scope it acts
    on) or exactly one :class:`ApiExempt`, never both. Each equivalent must
    name a registered ``/api`` operation (method and path template) whose
    route, the first in dispatch order that matches it, admits tokens. Each offender is one
    human-readable line.
    """
    api = _api_routes(app)
    offenders: list[str] = []
    for path, methods, dependant, _ in _walk(app.routes):
        mutating = sorted(methods - _SAFE)
        if path.startswith(_API_PREFIX) or not mutating:
            continue
        label = f"{'/'.join(mutating)} {path}"
        declarations = dependant_api_declarations(dependant)
        problem = _declaration_problem(declarations)
        if problem is not None:
            offenders.append(f"{label}: {problem}")
            continue
        for declared in declarations:
            if not isinstance(declared, ApiEquivalent):
                continue
            target = f"{declared.method} {declared.path}"
            admits = _resolve(api, declared)
            if admits is None:
                offenders.append(f"{label}: {target} is not a registered route")
            elif not admits:
                offenders.append(f"{label}: {target} refuses API tokens")
    return offenders
