"""Keycloak Inertia view routes — login page, logout."""

from __future__ import annotations

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse

router = APIRouter(tags=["keycloak-views"])

_SESSION_ID_TOKEN = "keycloak_id_token"


@router.get("/login")
async def login_page(request: Request, inertia: InertiaDep):
    return inertia.render("Keycloak/Login")


@router.post("/logout")
async def logout(request: Request):
    from keycloak.oidc import OIDCClient

    s = request.app.state.keycloak.settings
    id_token = request.session.get(_SESSION_ID_TOKEN)

    request.session.clear()

    client = OIDCClient(
        server_url=s.server_url,
        realm=s.realm,
        client_id=s.client_id,
        client_secret=s.client_secret,
    )
    base_url = str(request.base_url).rstrip("/")
    logout_url = client.build_logout_url(
        post_logout_redirect_uri=f"{base_url}/keycloak/login",
        id_token_hint=id_token,
    )
    return RedirectResponse(logout_url, status_code=303)
