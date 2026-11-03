"""Keycloak access-token adapter for shared browser renewal."""

import uuid

from auth.oidc_common.renewal import refresh_session
from auth.oidc_common.session import SessionKeys
from simple_module_db import independent_session
from sqlmodel import select

from keycloak.constants import (
    SESSION_ID_TOKEN_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_USER_KEY,
)
from keycloak.models import KeycloakUserCache
from keycloak.tokens import open_refresh_token, store_refresh_token

_KEYS = SessionKeys(
    SESSION_USER_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    "keycloak_refresh_attempted",
    obsolete=(SESSION_ID_TOKEN_KEY,),
)


class SessionRenewal:
    _forget_session = staticmethod(_KEYS.forget)

    async def _refresh_session(self, request):
        from keycloak.endpoints.api import _get_oidc_client

        async def refresh(token):
            return await _get_oidc_client(request).refresh_tokens(token)

        async def validate(tokens):
            return await self.jwks_cache.validate_jwt(tokens.get("access_token", ""))

        async def matches(claims, old_ctx):
            try:
                cache_id = uuid.UUID(old_ctx.id)
                async with independent_session(request.app) as db:
                    subject = (
                        await db.execute(
                            select(KeycloakUserCache.keycloak_sub).where(
                                KeycloakUserCache.id == cache_id
                            )
                        )
                    ).scalar_one_or_none()
                return subject is not None and subject == claims["sub"]
            except Exception:
                return False

        return await refresh_session(
            request,
            keys=_KEYS,
            cache=self.jwks_cache,
            open_token=open_refresh_token,
            store_token=store_refresh_token,
            refresh=refresh,
            validate=validate,
            matches_identity=matches,
            to_context=self._claims_to_user_context,
        )
