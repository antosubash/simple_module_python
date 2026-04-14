"""Auth API endpoints — OIDC login/callback/logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from sm_auth.oauth import oauth

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/login")
async def login(request: Request):
    """Redirect to Keycloak login page."""
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, str(redirect_uri))


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    """Handle Keycloak's redirect after successful login."""
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except Exception as e:
        # If token exchange fails (code expired, state mismatch, etc.)
        # clear session and redirect to landing page
        logger.warning("Auth callback failed: %s", e)
        request.session.clear()
        return RedirectResponse("/", status_code=302)

    # Only store minimal data in session cookie (browsers limit to ~4KB)
    userinfo = dict(token.get("userinfo", {}))
    # Keep only essential fields to stay under cookie size limit
    request.session["userinfo"] = {
        "sub": userinfo.get("sub"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "preferred_username": userinfo.get("preferred_username"),
        "realm_access": userinfo.get("realm_access", {}),
    }

    # Redirect to the original URL (or dashboard)
    next_url = request.session.pop("next", "/dashboard")
    return RedirectResponse(next_url, status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to Keycloak logout."""
    import urllib.parse

    auth_settings = request.app.state.auth_settings
    request.session.clear()

    params = {
        "client_id": auth_settings.keycloak_client_id,
        "post_logout_redirect_uri": str(request.base_url),
    }

    end_session_url = (
        f"{auth_settings.keycloak_url}/realms/{auth_settings.keycloak_realm}"
        f"/protocol/openid-connect/logout?{urllib.parse.urlencode(params)}"
    )
    return RedirectResponse(end_session_url, status_code=302)


@router.get("/me")
async def me(request: Request):
    """Return the current user's info from session."""
    userinfo = request.session.get("userinfo")
    if not userinfo:
        return {"authenticated": False}
    return {"authenticated": True, "user": userinfo}
