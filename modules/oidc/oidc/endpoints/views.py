"""OIDC interstitials and RP-initiated logout."""

import logging

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia.response import location
from starlette.responses import RedirectResponse

from oidc.constants import _PAGE_LOGGED_OUT, _PAGE_LOGIN, LOGGED_OUT_PATH
from oidc.session_state import is_signed_in

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
        return RedirectResponse(request.app.state.oidc.settings.login_redirect_url, 303)
    return await inertia.render(_PAGE_LOGGED_OUT)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    destination = f"{str(request.base_url).rstrip('/')}{LOGGED_OUT_PATH}"
    client = request.app.state.oidc.client
    if client is not None:
        try:
            destination = client.build_logout_url(post_logout_redirect_uri=destination)
        except Exception:
            logger.warning("OIDC logout unavailable; local session cleared")
    if request.headers.get("X-Inertia"):
        return location(destination)
    return RedirectResponse(destination, status_code=303)
