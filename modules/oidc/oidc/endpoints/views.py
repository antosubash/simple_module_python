"""OIDC Inertia view routes — login page, logout."""

from __future__ import annotations

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse

router = APIRouter(tags=["oidc-views"])

_SESSION_ID_TOKEN = "oidc_id_token"
_PAGE_LOGIN = "Oidc/Login"


@router.get("/login")
async def login_page(request: Request, inertia: InertiaDep):
    return await inertia.render(_PAGE_LOGIN)


@router.post("/logout")
async def logout(request: Request):
    client = request.app.state.oidc.client
    id_token = request.session.get(_SESSION_ID_TOKEN)

    request.session.clear()

    base_url = str(request.base_url).rstrip("/")
    post_logout = f"{base_url}/oidc/login"
    if client is None:
        return RedirectResponse(post_logout, status_code=303)

    logout_url = client.build_logout_url(
        post_logout_redirect_uri=post_logout,
        id_token_hint=id_token,
    )
    return RedirectResponse(logout_url, status_code=303)
