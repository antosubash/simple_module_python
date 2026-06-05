"""OIDC API endpoints — login redirect, callback."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["oidc-auth"])

_SESSION_OIDC_STATE = "oidc_state"
_SESSION_OIDC_NONCE = "oidc_nonce"
_SESSION_USER_CTX = "user_ctx"
_SESSION_ID_TOKEN = "oidc_id_token"
_SESSION_NEXT = "next"


def _require_client(request: Request):
    client = request.app.state.oidc.client
    if client is None:
        raise HTTPException(status_code=503, detail="OIDC provider not configured")
    return client


@router.get("/login")
async def oidc_login(request: Request):
    client = _require_client(request)
    s = request.app.state.oidc.settings
    callback_url = str(request.url_for("oidc_callback"))
    nonce = secrets.token_urlsafe(32)
    url, state = client.build_authorization_url(
        redirect_uri=callback_url,
        nonce=nonce,
        scope=s.scope,
    )
    request.session[_SESSION_OIDC_STATE] = state
    request.session[_SESSION_OIDC_NONCE] = nonce
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def oidc_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    expected_state = request.session.pop(_SESSION_OIDC_STATE, None)
    request.session.pop(_SESSION_OIDC_NONCE, None)

    if not code or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")

    client = _require_client(request)
    callback_url = str(request.url_for("oidc_callback"))

    try:
        tokens = await client.exchange_code(code=code, redirect_uri=callback_url)
    except Exception:
        logger.exception("Token exchange failed")
        raise HTTPException(status_code=502, detail="Token exchange failed") from None

    id_token = tokens.get("id_token", "")

    # Validate the id_token: aud == client_id across all OIDC providers, and the
    # reliable identity source for Entra (its access tokens aren't app-validatable).
    jwks_cache = request.app.state.oidc.jwks_cache
    claims = await jwks_cache.validate_jwt(id_token) if jwks_cache else None
    if claims is None:
        raise HTTPException(status_code=401, detail="Token validation failed")

    provider = request.app.state.auth.auth_provider
    cache_id = await provider._upsert_user_cache(request, claims)
    user_ctx = provider._claims_to_user_context(claims, cache_id=cache_id)

    request.session[_SESSION_USER_CTX] = user_ctx.to_session_dict()
    request.session[_SESSION_ID_TOKEN] = id_token

    s = request.app.state.oidc.settings
    next_url = request.session.pop(_SESSION_NEXT, None) or s.login_redirect_url
    return RedirectResponse(next_url, status_code=303)
