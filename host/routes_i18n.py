"""Locale switcher endpoint.

POST /i18n/set-locale with form body ``locale=<code>``. Validates against
the host's supported locales, sets a 1-year cookie, and 303-redirects to
a same-origin Referer (falls back to ``/`` for off-origin or missing).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from simple_module_hosting.redirects import safe_referer_or_root
from starlette.responses import RedirectResponse

router = APIRouter()

_ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


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

    destination = safe_referer_or_root(request)
    response = RedirectResponse(destination, status_code=303)
    # ``secure`` lets the cookie travel over HTTP in development (SM_SECRET_KEY
    # is the only thing that disambiguates dev vs. prod here); in production
    # the reverse proxy strips http traffic, so the flag is safe to always set.
    response.set_cookie(
        key=cookie_name,
        value=locale,
        max_age=_ONE_YEAR_SECONDS,
        path="/",
        samesite="lax",
        secure=request.url.scheme == "https",
        httponly=False,
    )
    return response
