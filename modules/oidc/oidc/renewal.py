"""Renew browser authority at ID-token expiry without retaining the ID token."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from auth.contracts.schemas import UserContext
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from starlette.requests import Request

from oidc.constants import SESSION_IDENTITY_KEY, SESSION_USER_KEY
from oidc.tokens import SESSION_REFRESH_TOKEN_KEY, open_refresh_token, seal_refresh_token

logger = logging.getLogger(__name__)
_RETRYABLE_STATUSES = frozenset({408, 425, 429})


class SessionRenewal:
    @staticmethod
    def _forget_session(session: Any) -> None:
        for key in (
            SESSION_USER_KEY,
            SESSION_REFRESH_TOKEN_KEY,
            SESSION_EXPIRES_AT_KEY,
            SESSION_IDENTITY_KEY,
        ):
            session.pop(key, None)

    async def _refresh_session(self, request: Request) -> UserContext | None:
        """Renew an expired session with a refresh grant; sign it out if that is refused.

        A transient failure (network error, 5xx) signs this request out but keeps
        the session, so the next request retries instead of losing the sign-in.
        """
        from oidc.endpoints.api import _require_client

        session = request.scope.get("session", {})
        sealed = session.get(SESSION_REFRESH_TOKEN_KEY)
        refresh_token = open_refresh_token(request.app, sealed) if sealed else None
        old_ctx = UserContext.from_session_dict(session.get(SESSION_USER_KEY))
        if not refresh_token or old_ctx is None or self.jwks_cache is None:
            self._forget_session(session)
            return None
        if getattr(request.state, "oidc_refresh_attempted", False):
            return None
        request.state.oidc_refresh_attempted = True
        try:
            tokens = await (await _require_client(request)).refresh_tokens(refresh_token)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            # Never log the exception text or body: token endpoints can echo credentials.
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            logger.warning("OIDC session refresh failed (status=%s)", status)
            if status is None or status >= 500 or status in _RETRYABLE_STATUSES:
                return None
            self._forget_session(session)
            return None
        except Exception:
            logger.warning("OIDC session refresh failed")
            self._forget_session(session)
            return None
        claims = await self.jwks_cache.validate_jwt(
            tokens.get("id_token", ""), audience=self._settings.client_id
        )
        expires_at = claims.get("exp") if claims else None
        if (
            not claims
            or not claims.get("sub")
            or type(expires_at) is not int
            or expires_at <= time.time()
        ):
            self._forget_session(session)
            return None
        try:
            identity = list(self._identity(claims))
        except ValueError:
            self._forget_session(session)
            return None
        if identity != session.get(SESSION_IDENTITY_KEY):
            self._forget_session(session)
            return None
        ctx = self._claims_to_user_context(claims, cache_id=old_ctx.id)
        session[SESSION_USER_KEY] = ctx.to_session_dict()
        new_refresh = tokens.get("refresh_token") or refresh_token
        session[SESSION_REFRESH_TOKEN_KEY] = seal_refresh_token(request.app, new_refresh)
        session[SESSION_EXPIRES_AT_KEY] = expires_at
        return ctx
