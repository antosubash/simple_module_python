"""Keycloak OIDC API endpoints — login redirect, callback."""

from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from simple_module_hosting.csrf import rotate_csrf_token
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY, sign_in_preserved_keys
from starlette.responses import RedirectResponse

if TYPE_CHECKING:
    from keycloak.settings import KeycloakSettings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["keycloak-auth"])

_SESSION_OIDC_STATE = "keycloak_oidc_state"
_SESSION_OIDC_NONCE = "keycloak_oidc_nonce"
_SESSION_USER_CTX = "user_ctx"
_SESSION_REFRESH_TOKEN = "keycloak_refresh_token"


def _get_settings(request: Request) -> KeycloakSettings:
    return request.app.state.keycloak.settings


def _get_oidc_client(request: Request):
    from keycloak.oidc import OIDCClient

    s = _get_settings(request)
    return OIDCClient(
        server_url=s.server_url,
        realm=s.realm,
        client_id=s.client_id,
        client_secret=s.client_secret,
    )


@router.get("/login")
async def oidc_login(request: Request):
    client = _get_oidc_client(request)
    callback_url = str(request.url_for("oidc_callback"))
    nonce = secrets.token_urlsafe(32)
    url, state = client.build_authorization_url(
        redirect_uri=callback_url,
        nonce=nonce,
    )
    request.session[_SESSION_OIDC_STATE] = state
    request.session[_SESSION_OIDC_NONCE] = nonce
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def oidc_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    expected_state = request.session.pop(_SESSION_OIDC_STATE, None)
    expected_nonce = request.session.pop(_SESSION_OIDC_NONCE, None)

    if not code or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")
    if not isinstance(expected_nonce, str) or not expected_nonce:
        raise HTTPException(status_code=400, detail="Missing OIDC nonce")

    client = _get_oidc_client(request)
    callback_url = str(request.url_for("oidc_callback"))

    try:
        tokens = await client.exchange_code(code=code, redirect_uri=callback_url)
    except Exception:
        logger.exception("Token exchange failed")
        raise HTTPException(status_code=502, detail="Token exchange failed") from None

    id_token = tokens.get("id_token", "")
    access_token = tokens.get("access_token", "")

    jwks_cache = request.app.state.keycloak.jwks_cache
    claims = await jwks_cache.validate_jwt(access_token) if jwks_cache else None
    if claims is None:
        raise HTTPException(status_code=401, detail="Token validation failed")

    id_claims = await jwks_cache.validate_jwt(id_token)
    nonce = id_claims.get("nonce") if id_claims else None
    if (
        not id_claims
        or not isinstance(nonce, str)
        or not secrets.compare_digest(nonce.encode(), expected_nonce.encode())
        or not claims.get("sub")
        or id_claims.get("sub") != claims["sub"]
    ):
        raise HTTPException(status_code=401, detail="ID token validation failed")

    expires_at = claims.get("exp")
    if type(expires_at) is not int or expires_at <= time.time():
        raise HTTPException(status_code=401, detail="Invalid access token expiry")

    provider = request.app.state.auth.auth_provider
    cache_id = await provider._upsert_user_cache(request, claims)
    user_ctx = provider._claims_to_user_context(claims, cache_id=cache_id)

    s = _get_settings(request)
    # Sanitised on the way out as well as in: this value lands in a
    # Location header, and defence in depth costs one call.
    next_url = (
        safe_next_or_none(request.session.pop(SESSION_NEXT_KEY, None)) or s.login_redirect_url
    )
    preserved = {
        key: request.session[key]
        for key in sign_in_preserved_keys(request.app)
        if key in request.session
    }
    request.session.clear()
    request.session.update(preserved)
    rotate_csrf_token(request)
    request.session[_SESSION_USER_CTX] = user_ctx.to_session_dict()
    # Keep the signed cookie below browser limits: validate, but don't store, the ID token.
    if tokens.get("refresh_token"):
        request.session[_SESSION_REFRESH_TOKEN] = tokens["refresh_token"]
    request.session[SESSION_EXPIRES_AT_KEY] = expires_at
    return RedirectResponse(next_url, status_code=303)
