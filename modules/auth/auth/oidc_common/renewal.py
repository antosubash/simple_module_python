"""Renew browser authority at token expiry without retaining identity tokens."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from starlette.requests import Request

from auth.constants import REFRESH_RETRY_AFTER_SECONDS
from auth.contracts.schemas import UserContext
from auth.oidc_common.renewal_outcomes import coordinated_refresh
from auth.oidc_common.session import SessionKeys

logger = logging.getLogger(__name__)
_RETRYABLE_STATUSES = frozenset({408, 425, 429})


async def refresh_session(
    request: Request,
    *,
    keys: SessionKeys,
    cache: Any,
    open_token: Any,
    store_token: Any,
    refresh: Any,
    validate: Any,
    matches_identity: Any,
    to_context: Any,
) -> UserContext | None:
    """Renew bounded authority, preserving transient failures with a retry cooldown."""
    session = request.scope.get("session", {})
    sealed = session.get(keys.refresh)
    refresh_token = open_token(request.app, sealed) if sealed else None
    old_ctx = UserContext.from_session_dict(session.get(keys.user))
    if not refresh_token or old_ctx is None or cache is None:
        keys.forget(session)
        return None
    if getattr(request.state, keys.attempted, False):
        return None
    retry_at = session.get(keys.retry)
    if type(retry_at) is int and retry_at > time.time():
        return None
    setattr(request.state, keys.attempted, True)

    async def renew():
        return await _refresh_grant(
            request,
            keys=keys,
            refresh_token=refresh_token,
            old_ctx=old_ctx,
            store_token=store_token,
            refresh=refresh,
            validate=validate,
            matches_identity=matches_identity,
            to_context=to_context,
        )

    return await coordinated_refresh(request, keys, sealed, renew)


async def _refresh_grant(
    request,
    *,
    keys,
    refresh_token,
    old_ctx,
    store_token,
    refresh,
    validate,
    matches_identity,
    to_context,
):
    session = request.session
    try:
        tokens = await refresh(refresh_token)
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        # Never log the exception text or body: token endpoints can echo credentials.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning("OIDC session refresh failed (status=%s)", status)
        if status is None or status >= 500 or status in _RETRYABLE_STATUSES:
            session[keys.retry] = int(time.time()) + REFRESH_RETRY_AFTER_SECONDS
            return None
        keys.forget(session)
        return None
    except Exception:
        logger.warning("OIDC session refresh failed")
        keys.forget(session)
        return None
    if not isinstance(tokens, dict):
        keys.forget(session)
        return None
    claims = await validate(tokens)
    expires_at = claims.get("exp") if claims else None
    if (
        not claims
        or not claims.get("sub")
        or type(expires_at) is not int
        or expires_at <= time.time()
    ):
        keys.forget(session)
        return None
    if not await matches_identity(claims, old_ctx):
        keys.forget(session)
        return None
    ctx = to_context(claims, cache_id=old_ctx.id)
    session[keys.user] = ctx.to_session_dict()
    session.pop(keys.retry, None)
    for key in keys.obsolete:
        session.pop(key, None)
    session[SESSION_EXPIRES_AT_KEY] = expires_at
    store_token(request.app, session, tokens.get("refresh_token") or refresh_token)
    return ctx
