"""OIDC interstitials and RP-initiated logout."""

import logging

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia.response import location
from starlette.responses import RedirectResponse

from oidc.constants import _PAGE_LOGGED_OUT, _PAGE_LOGIN, LOGGED_OUT_PATH

logger = logging.getLogger(__name__)
router = APIRouter(tags=["oidc-views"])


@router.get("/login")
async def login_page(inertia: InertiaDep):
    return await inertia.render(_PAGE_LOGIN)


@router.get("/logged-out")
async def logged_out_page(inertia: InertiaDep):
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
