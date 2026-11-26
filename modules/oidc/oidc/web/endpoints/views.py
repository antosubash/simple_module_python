"""OIDC interstitials and RP-initiated logout."""

import logging

from auth.oidc_common.logout import logout_event_for
from auth.oidc_common.renewal_outcomes import forget_outcomes
from fastapi import APIRouter, Depends, Request
from simple_module_hosting.auth.auth_policy import login_redirect_url
from simple_module_hosting.auth.csrf import require_browser_origin
from simple_module_hosting.frontend.inertia_deps import InertiaDep, is_inertia_request
from simple_module_inertia.protocol.response import location
from starlette.background import BackgroundTask
from starlette.responses import RedirectResponse

from oidc.core.constants import (
    _PAGE_LOGGED_OUT,
    _PAGE_LOGIN,
    LOGGED_OUT_PATH,
    SESSION_REFRESH_TOKEN_KEY,
)
from oidc.core.runtime import is_signed_in
from oidc.identity.provider import OidcAuthProvider
from oidc.identity.renewal import _KEYS
from oidc.identity.tokens import open_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["oidc-views"])


@router.get("/login")
async def login_page(inertia: InertiaDep):
    return await inertia.render(_PAGE_LOGIN)


@router.get("/logged-out")
async def logged_out_page(request: Request, inertia: InertiaDep):
    # Only meaningful once the session is gone; a signed-in visitor is not
    # told they were signed out.
    if is_signed_in(request.session):
        return RedirectResponse(login_redirect_url(request.app, "Oidc"), 303)
    return await inertia.render(_PAGE_LOGGED_OUT)


@router.post("/logout", dependencies=[Depends(require_browser_origin)])
async def logout(request: Request):
    event = await logout_event_for(request, OidcAuthProvider)
    client = request.app.state.oidc.client
    if client is not None:
        try:
            refresh_token = open_refresh_token(
                request.app, request.session.get(SESSION_REFRESH_TOKEN_KEY)
            )
            if refresh_token:
                await client.revoke_refresh_token(refresh_token)
        except Exception as exc:
            # The class (timeout, HTTP status error, ...), never the token or body.
            logger.warning(
                "OIDC refresh token revocation failed (%s); continuing logout", type(exc).__name__
            )
    await forget_outcomes(request.app, _KEYS, request.session)
    request.session.clear()
    destination = f"{str(request.base_url).rstrip('/')}{LOGGED_OUT_PATH}"
    if client is not None:
        try:
            destination = client.build_logout_url(post_logout_redirect_uri=destination)
        except Exception:
            logger.warning("OIDC logout unavailable; local session cleared")
    if is_inertia_request(request.scope):
        response = location(destination)
    else:
        response = RedirectResponse(destination, status_code=303)
    if event is not None:
        response.background = BackgroundTask(request.app.state.sm.event_bus.publish, event)
    return response
