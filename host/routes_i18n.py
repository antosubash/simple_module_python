"""Locale switcher endpoint.

POST /i18n/set-locale with form body ``locale=<code>``. Validates against
the host's supported locales, sets a 1-year cookie, and 303-redirects to
a same-origin Referer (falls back to ``/`` for off-origin or missing).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import RedirectResponse

router = APIRouter()

_ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


def _safe_redirect_target(request: Request) -> str:
    """Return the Referer iff it's same-origin; otherwise fall back to ``/``.

    An attacker can control the ``Referer`` header (e.g. via a crafted form on
    a third-party site). We only honor references that (a) resolve to the
    same scheme+host as the current request, or (b) are relative paths that
    don't try to escape to a protocol-relative URL (``//evil.example``).
    """
    referer = request.headers.get("referer")
    if not referer:
        return "/"

    # Reject protocol-relative URLs like "//evil.example/foo" that browsers
    # would resolve against the origin but a crafted Referer could use to
    # leave the site.
    if referer.startswith("//"):
        return "/"

    parsed = urlsplit(referer)
    # Relative path with no scheme+host → same-origin by construction.
    if not parsed.scheme and not parsed.netloc:
        return referer if referer.startswith("/") else "/"

    # Absolute URL → must match the current request's origin.
    current = request.url
    if parsed.scheme == current.scheme and parsed.netloc == current.netloc:
        # Preserve the path + query.
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    return "/"


@router.post("/i18n/set-locale", response_model=None)
async def set_locale(request: Request, locale: str = Form(...)) -> RedirectResponse:
    """Persist the user's locale choice in a long-lived cookie.

    Validates the requested locale against ``available_locales()`` (locales
    with loaded messages) rather than the raw configured supported list, so
    the endpoint can't accept a locale that would render a blank UI.
    """
    registry = getattr(request.app.state, "i18n_registry", None)
    if registry is not None:
        supported = registry.available_locales()
    else:
        # Fallback for tests that build a minimal app without the registry.
        supported = request.app.state.settings_supported_locales
    cookie_name: str = request.app.state.settings_cookie_name

    if locale not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported locale '{locale}' (available: {', '.join(supported)})",
        )

    destination = _safe_redirect_target(request)
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(
        key=cookie_name,
        value=locale,
        max_age=_ONE_YEAR_SECONDS,
        path="/",
        samesite="lax",
        httponly=False,
    )
    return response
