"""Framework-wide exception handlers that render Inertia error pages."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.exceptions import NotFoundError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from simple_module_hosting._inertia_shared import _INERTIA_HEADER
from simple_module_hosting._inertia_url import relative_page_url_dependency
from simple_module_hosting.permissions import PERMISSION_DENIED_PREFIX

logger = logging.getLogger(__name__)

_INERTIA_ERROR_STATUSES = frozenset({401, 403, 404, 419, 422, 429, 500, 503})

# Statuses whose remedy is "sign in", so the page offers that as its primary
# action rather than sending the visitor to the landing page.
_SIGN_IN_STATUSES = frozenset({401, 419})


def _specific_detail(status_code: int, message: str) -> str:
    """The detail, unless it only restates the status.

    Starlette defaults ``HTTPException.detail`` to ``HTTPStatus(code).phrase``,
    so a plain ``HTTPException(404)`` reaches the page carrying "Not Found" and
    a bare ``HTTPException(403)`` carrying "Forbidden". The page prefers a
    server message over its own catalog description — right when the message
    says something ("Administrator access required"), useless when it is the
    title again in Title Case, and it made the page's own 404/403 sentences
    unreachable on the very paths that produce them.

    Only an exact, case-insensitive match is dropped: anything a caller
    actually wrote survives, including a sentence that merely starts with the
    phrase. Non-standard codes (419) have no phrase to collide with.
    """
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return message
    return "" if message.strip().casefold() == phrase.casefold() else message


def _required_permission(message: str) -> str | None:
    """The permission named by a ``RequiresPermission`` denial, if this is one.

    The 403 page says "Your role doesn't include ``<perm>``. Ask an admin to
    grant it." — it needs the bare permission name, not the sentence the guard
    wrote for logs and API clients. Reading it back off the detail (using the
    guard's own exported prefix) keeps ``RequiresPermission`` as the single
    place that knows the name; the alternative, stashing it on
    ``request.state``, only works when the exception travels the one code path
    that set it, and 403s are also raised by hand.

    Anything else — a role-gated ``/admin`` 403, a hand-raised
    ``HTTPException(403, "Administrator access required")`` — yields ``None``,
    and the page falls back to copy that names no permission.
    """
    if not message.startswith(PERMISSION_DENIED_PREFIX):
        return None
    return message[len(PERMISSION_DENIED_PREFIX) :].strip() or None


def _login_url(request: Request) -> str | None:
    """Best-effort login URL for the sign-in statuses.

    Read off ``app.state`` rather than imported: the auth provider is a plugin
    concern and ``SM009`` forbids framework code importing ``modules/*``. An
    app with no auth provider installed simply gets no sign-in button.
    """
    auth_state = getattr(request.app.state, "auth", None)
    provider = getattr(auth_state, "auth_provider", None)
    if provider is None:
        return None
    try:
        return provider.get_login_url(request)
    except Exception:
        # A broken provider must not turn an error page into a second error.
        logger.exception("Auth provider failed to supply a login URL")
        return None


def _explicit_accept_q(accept: str, media_type: str) -> float | None:
    """Quality the Accept header gives ``media_type`` by explicit listing, or
    ``None`` when the caller never named it at all.

    Only exact entries count (no ``*/*`` / ``type/*`` wildcards) — the
    negotiation below cares whether the caller *named* html or json, and at
    what preference, and separately whether they named it *at all* (``None``
    vs. an explicit ``q=0``). Malformed q-values fall back to 1.0 per RFC 9110.
    """
    for part in accept.split(","):
        media, _, params = part.partition(";")
        if media.strip().lower() != media_type:
            continue
        q = 1.0
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    q = float(value.strip())
                except ValueError:
                    q = 1.0
        return q
    return None


def _wants_json(request: Request) -> bool:
    """API callers get JSON error bodies; browser-shaped requests get the page.

    A request that explicitly accepts ``text/html`` is a browser navigation —
    and those reach ``/api/*`` too (OAuth login links, file-download hrefs) —
    so it always gets the rendered page, unless the caller *prefers* JSON via
    q-values (``application/json, text/html;q=0.5`` is an API client keeping
    an html fallback). So does an Inertia visit (``X-Inertia`` header),
    whatever its Accept — an Inertia client can only consume Inertia-protocol
    responses, never a bare JSON body. Otherwise ``/api/*``, the documented
    prefix for every module's JSON surface (``ModuleMeta.route_prefix``),
    gets JSON — a bare ``fetch()`` sends ``Accept: */*`` — as does an
    explicit ``Accept: application/json`` anywhere else.

    ``text/html;q=0`` rules html out *everywhere*, not just under ``/api/*``:
    once the caller has explicitly said they won't accept html, this never
    chooses the html page. The (already-moot) html fallback survives only
    when json wasn't mentioned either — there's nothing else to offer, so a
    view path keeps its pre-existing default and an ``/api/*`` path keeps
    getting JSON either way.
    """
    if request.headers.get(_INERTIA_HEADER):
        return False
    accept = request.headers.get("accept", "")
    html_q = _explicit_accept_q(accept, "text/html")
    json_q = _explicit_accept_q(accept, "application/json")
    if html_q is not None and html_q > 0 and html_q >= (json_q or 0.0):
        return False
    path = request.url.path
    is_api = path == "/api" or path.startswith("/api/")
    if html_q == 0:
        return is_api if json_q is None else True
    return is_api or bool(json_q)


async def render_error_page(
    request: Request,
    status_code: int,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """Render the Inertia error page for *status_code*.

    ``headers`` carries an ``HTTPException``'s own headers through to the
    response. A rendered page is still the same status as the JSON body it
    replaces, so ``WWW-Authenticate`` on a 401 and ``Retry-After`` on a
    429/503 have to survive the switch — widening the set of statuses that
    render a page must not quietly narrow what those responses carry.
    """
    try:
        # Inside the try, not above it: this lookup is exactly the kind of
        # thing that is missing when the app is half-built, and an error page
        # that raises while reporting an error leaves the caller with nothing.
        config: InertiaConfig = request.app.state.sm.inertia_config
        # Prefer the app's configured dependency over constructing Inertia
        # directly: it carries the framework's wraps, and an error page built
        # around them is an error page rendered differently from every other
        # page. That is how the 404 kept throwing the cross-scheme `pushState`
        # SecurityError after the page url was made relative everywhere else.
        # The raw construction stays as the fallback for a half-built app —
        # the case this whole handler exists to survive — but still goes
        # through the same url-relativizing wrap directly: a fallback that
        # skipped it would reintroduce the exact bug this module exists to
        # fix, just for the one request that hit it before setup finished.
        inertia_dep = getattr(request.app.state, "inertia_dependency", None)
        if inertia_dep is None:
            inertia_dep = relative_page_url_dependency(
                lambda req, client=None: Inertia(req, config)
            )
        inertia = inertia_dep(request, None)
        # This does not go through get_inertia, so the share step has to be
        # repeated here. Without it the error page renders raw translation keys
        # (host.error.not_found_title) and loses auth/menus, so a signed-in
        # user's 404 has no layout.
        shared = getattr(request.state, "inertia_shared", None)
        if shared:
            inertia.share(**shared)
        # The correlation id is the only handle a user has on their own failed
        # request — without it a support report is just "it broke". It is already
        # on every log line for this request, so quoting it back makes the page
        # and the logs joinable.
        response = await inertia.render(
            "Error",
            {
                "status": status_code,
                # Not the raw detail: a default one is just the status phrase,
                # and the page renders any message it is given ahead of its own
                # copy. See `_specific_detail`.
                "message": _specific_detail(status_code, message),
                "correlation_id": getattr(request.state, "correlation_id", "") or "",
                # Always present, null when no permission is involved: the page
                # branches on it, and an absent prop is indistinguishable there
                # from one that was never wired.
                "required_permission": _required_permission(message),
                "login_url": (_login_url(request) if status_code in _SIGN_IN_STATUSES else None),
                # Set by MaintenanceMiddleware. A planned outage reads very
                # differently from the same status code arriving unbidden.
                "maintenance": bool(getattr(request.state, "maintenance", False)),
            },
        )
        response.status_code = status_code
        _apply_headers(response, headers)
        return response
    except InertiaVersionConflictException as exc:
        return await inertia_version_conflict_exception_handler(request, exc)
    except Exception:
        # Fallback if Inertia rendering itself fails (e.g. missing session)
        logger.exception("Error page rendering failed, falling back to JSON")
        return JSONResponse(
            status_code=status_code,
            content={"detail": message or "Internal Server Error"},
            headers=dict(headers) if headers else None,
        )


def _apply_headers(response: Response, headers: Mapping[str, str] | None) -> None:
    """Copy exception headers onto an already-built response.

    Set rather than appended: these are single-valued response headers, and
    a duplicate ``Retry-After`` is worse than none.
    """
    if not headers:
        return
    for key, value in headers.items():
        response.headers[key] = value


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    # Preserve exception headers (WWW-Authenticate, Retry-After, ...) the way
    # FastAPI's stock handler does — on the rendered page as well as the JSON
    # body, since both answer with the same status.
    headers = getattr(exc, "headers", None)
    if exc.status_code in _INERTIA_ERROR_STATUSES and not _wants_json(request):
        detail = str(exc.detail) if exc.detail else ""
        return await render_error_page(request, exc.status_code, detail, headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


async def not_found_error_handler(request: Request, exc: NotFoundError) -> Response:
    if _wants_json(request):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    return await render_error_page(request, 404, str(exc))


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Return an Inertia error page for browser requests with invalid params.

    Same negotiation rule as 403/404/500 (``_wants_json``), so one request
    never sees two different error shapes depending on the error class.
    """
    if _wants_json(request):
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
    return await render_error_page(request, 422, "The requested URL contains invalid parameters.")


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled exception: %s", exc)
    if _wants_json(request):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return await render_error_page(request, 500, "")
