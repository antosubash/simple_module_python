"""Render error responses without depending on handlers or middleware wiring."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi.responses import JSONResponse
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

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


async def render_error_page(
    request: Request,
    status_code: int,
    message: str,
    headers: Mapping[str, str] | None = None,
    required_permission: str | None = None,
) -> Response:
    """Render the Inertia error page for *status_code*.

    ``required_permission`` names the permission a 403 lacked (from
    :class:`PermissionDenied`); the page words its own sentence around it.

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
        # directly, so the error page is built the same way as every other
        # page. The raw construction is the fallback for a half-built app —
        # the case this whole handler exists to survive. Both paths emit a
        # root-relative page url: the adapter does that by construction now,
        # so the fallback no longer needs a separate patch to avoid the
        # cross-scheme `pushState` SecurityError behind a TLS proxy.
        inertia_dep = getattr(request.app.state, "inertia_dependency", None)
        if inertia_dep is not None:
            inertia = inertia_dep(request, None)
        else:
            inertia = Inertia(request, config)
        # This does not go through get_inertia, so the share step has to be
        # repeated here. Without it the error page renders raw translation keys
        # (ui.error_page.not_found_title) and loses auth/menus, so a signed-in
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
                "required_permission": required_permission,
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
