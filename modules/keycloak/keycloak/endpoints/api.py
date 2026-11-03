"""Keycloak OIDC API endpoints — login redirect, callback."""

from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING

from auth.oidc_common.session import sign_in, stale_callback
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from keycloak.constants import (
    SESSION_NONCE_KEY as _SESSION_OIDC_NONCE,
)
from keycloak.constants import (
    SESSION_STATE_KEY as _SESSION_OIDC_STATE,
)
from keycloak.constants import (
    SESSION_USER_KEY as _SESSION_USER_CTX,
)
from keycloak.constants import (
    SESSION_VERIFIER_KEY,
)
from keycloak.tokens import store_refresh_token

if TYPE_CHECKING:
    from keycloak.settings import KeycloakSettings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["keycloak-auth"])


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
    verifier = secrets.token_urlsafe(64)
    url, state = client.build_authorization_url(
        redirect_uri=callback_url,
        nonce=nonce,
        code_verifier=verifier,
    )
    request.session[_SESSION_OIDC_STATE] = state
    request.session[_SESSION_OIDC_NONCE] = nonce
    request.session[SESSION_VERIFIER_KEY] = verifier
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def oidc_callback(request: Request):
    code = request.query_params.get("code")
    stale = stale_callback(
        request, _SESSION_OIDC_STATE, _SESSION_USER_CTX, _get_settings(request).login_redirect_url
    )
    if stale is not None:
        return stale
    request.session.pop(_SESSION_OIDC_STATE, None)
    expected_nonce = request.session.pop(_SESSION_OIDC_NONCE, None)
    verifier = request.session.pop(SESSION_VERIFIER_KEY, None)
    if request.query_params.get("error"):
        raise HTTPException(status_code=401, detail="Sign-in was refused by the identity provider")
    if not code:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")
    if not isinstance(expected_nonce, str) or not expected_nonce:
        raise HTTPException(status_code=400, detail="Missing OIDC nonce")

    if not isinstance(verifier, str) or not verifier:
        # A login started before the PKCE upgrade: same as a stale callback.
        raise HTTPException(status_code=419, detail="Sign-in expired; start again")
    client = _get_oidc_client(request)
    callback_url = str(request.url_for("oidc_callback"))

    try:
        tokens = await client.exchange_code(
            code=code, redirect_uri=callback_url, code_verifier=verifier
        )
    except Exception:
        logger.warning("Token exchange failed")
        raise HTTPException(status_code=502, detail="Token exchange failed") from None

    if not isinstance(tokens, dict):
        raise HTTPException(status_code=502, detail="Token exchange failed")
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
    next_url = sign_in(
        request,
        user=user_ctx,
        expires_at=expires_at,
        redirect=s.login_redirect_url,
        user_key=_SESSION_USER_CTX,
    )
    if tokens.get("refresh_token"):
        store_refresh_token(request.app, request.session, tokens["refresh_token"])
    return RedirectResponse(next_url, status_code=303)
