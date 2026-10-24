"""Keycloak Inertia view routes — redirect interstitial, logout, signed-out card."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse

from keycloak.tokens import SESSION_REFRESH_TOKEN_KEY, open_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["keycloak-views"])

_PAGE_LOGIN = "Keycloak/Login"
_PAGE_LOGGED_OUT = "Keycloak/LoggedOut"
_LOGGED_OUT_PATH = "/keycloak/logged-out"


def _realm_url(request: Request) -> str:
    """Where the browser is being sent, for the card to name.

    Blank when the realm is not configured yet — the interstitial then says it
    is redirecting without naming a host it cannot vouch for.
    """
    s = request.app.state.keycloak.settings
    if not s.server_url or not s.realm:
        return ""
    return f"{s.server_url.rstrip('/')}/realms/{s.realm}"


@router.get("/login")
async def login_page(request: Request, inertia: InertiaDep):
    return await inertia.render(_PAGE_LOGIN, {"realm_url": _realm_url(request)})


@router.get("/logged-out")
async def logged_out_page(inertia: InertiaDep):
    """The card Keycloak lands on after ending both sessions.

    ``pages/LoggedOut.tsx`` shipped with no route pointing at it, so signing
    out bounced straight back to the redirect interstitial and immediately
    signed you in again. Public by registration in ``provider.py``: by
    definition nobody holds a session here.
    """
    return await inertia.render(_PAGE_LOGGED_OUT)


@router.post("/logout")
async def logout(request: Request):
    from keycloak.oidc import OIDCClient

    s = request.app.state.keycloak.settings
    refresh_token = open_refresh_token(request.app, request.session.get(SESSION_REFRESH_TOKEN_KEY))
    request.session.clear()

    client = OIDCClient(
        server_url=s.server_url,
        realm=s.realm,
        client_id=s.client_id,
        client_secret=s.client_secret,
    )
    if refresh_token:
        # Without an id_token_hint the browser redirect alone may only show a
        # confirmation page, so end the SSO session back-channel first.
        try:
            await client.revoke_session(refresh_token)
        except Exception:
            # Never log the exception text: it may carry request details.
            logger.warning("Keycloak back-channel logout failed")
    base_url = str(request.base_url).rstrip("/")
    logout_url = client.build_logout_url(
        post_logout_redirect_uri=f"{base_url}{_LOGGED_OUT_PATH}",
    )
    return RedirectResponse(logout_url, status_code=303)
