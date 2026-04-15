"""Locale switcher endpoint.

POST /i18n/set-locale with form body ``locale=<code>``. Validates against
the host's supported locales, sets a 1-year cookie, and 303-redirects to
the Referer (falls back to ``/``).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import RedirectResponse

router = APIRouter()

_ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


@router.post("/i18n/set-locale", response_model=None)
async def set_locale(request: Request, locale: str = Form(...)) -> RedirectResponse:
    """Persist the user's locale choice in a long-lived cookie."""
    supported: list[str] = request.app.state.settings_supported_locales
    cookie_name: str = request.app.state.settings_cookie_name

    if locale not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported locale '{locale}' (supported: {', '.join(supported)})",
        )

    destination = request.headers.get("referer") or "/"
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
