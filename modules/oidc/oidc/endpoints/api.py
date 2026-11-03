"""OIDC login transaction: PKCE, nonce, session rotation and bounded authority."""

from __future__ import annotations

import logging
import secrets
import time

from auth.oidc_common.session import sign_in, stale_callback
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from oidc.constants import (
    SESSION_IDENTITY_KEY,
    SESSION_NONCE_KEY,
    SESSION_STATE_KEY,
    SESSION_USER_KEY,
    SESSION_VERIFIER_KEY,
)
from oidc.runtime import require_client
from oidc.tokens import store_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["oidc-auth"])


@router.get("/login", name="oidc_auth_login")
async def oidc_login(request: Request):
    client = await require_client(request)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    url, state = client.build_authorization_url(
        redirect_uri=str(request.url_for("oidc_auth_callback")),
        nonce=nonce,
        scope=request.app.state.oidc.settings.scope,
        code_verifier=verifier,
    )
    request.session[SESSION_STATE_KEY] = state
    request.session[SESSION_NONCE_KEY] = nonce
    request.session[SESSION_VERIFIER_KEY] = verifier
    return RedirectResponse(url, status_code=302)


@router.get("/callback", name="oidc_auth_callback")
async def oidc_callback(request: Request):
    code = request.query_params.get("code")
    # The state is compared before the login transaction is consumed: a reply
    # that does not carry it (a forged link) leaves the pending sign-in alone.
    stale = stale_callback(
        request,
        SESSION_STATE_KEY,
        SESSION_USER_KEY,
        request.app.state.oidc.settings.login_redirect_url,
    )
    if stale is not None:
        return stale
    request.session.pop(SESSION_STATE_KEY, None)
    expected_nonce = request.session.pop(SESSION_NONCE_KEY, None)
    verifier = request.session.pop(SESSION_VERIFIER_KEY, None)
    # Past this point the reply belongs to this login, and every outcome,
    # including an ``error`` reply (access_denied, login_required, ...), spends it.
    if request.query_params.get("error"):
        raise HTTPException(status_code=401, detail="Sign-in was refused by the identity provider")
    if not code:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")
    if not isinstance(expected_nonce, str) or not expected_nonce:
        raise HTTPException(status_code=400, detail="Missing OIDC nonce")
    if not isinstance(verifier, str) or not verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE verifier")
    client = await require_client(request)
    try:
        tokens = await client.exchange_code(
            code=code,
            redirect_uri=str(request.url_for("oidc_auth_callback")),
            code_verifier=verifier,
        )
    except Exception:
        logger.warning("OIDC token exchange failed")
        raise HTTPException(status_code=502, detail="Token exchange failed") from None
    if not isinstance(tokens, dict):
        logger.warning("OIDC token endpoint returned a non-object response")
        raise HTTPException(status_code=502, detail="Token exchange failed")
    s = request.app.state.oidc.settings
    cache = request.app.state.oidc.jwks_cache
    claims = (
        await cache.validate_jwt(tokens.get("id_token", ""), audience=s.client_id)
        if cache
        else None
    )
    nonce = claims.get("nonce") if claims else None
    if not isinstance(nonce, str) or not secrets.compare_digest(
        nonce.encode(), expected_nonce.encode()
    ):
        raise HTTPException(status_code=401, detail="ID token validation failed")
    expires_at = claims.get("exp")
    if type(expires_at) is not int or expires_at <= time.time():
        raise HTTPException(status_code=401, detail="Invalid ID token expiry")
    provider = request.app.state.auth.auth_provider
    try:
        identity = provider._identity(claims)
    except ValueError:
        raise HTTPException(status_code=401, detail="Missing OIDC identity") from None
    cache_id = await provider._upsert_user_cache(request, claims)
    if cache_id is None:
        raise HTTPException(status_code=503, detail="OIDC identity unavailable")
    user_ctx = provider._claims_to_user_context(claims, cache_id=cache_id)
    next_url = sign_in(
        request,
        user=user_ctx,
        expires_at=expires_at,
        redirect=s.login_redirect_url,
        user_key=SESSION_USER_KEY,
        identity_key=SESSION_IDENTITY_KEY,
        identity=identity,
    )
    if tokens.get("refresh_token"):
        store_refresh_token(request.app, request.session, tokens["refresh_token"])
    return RedirectResponse(next_url, status_code=303)
