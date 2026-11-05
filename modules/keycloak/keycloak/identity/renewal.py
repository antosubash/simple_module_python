"""Keycloak access-token adapter for shared browser renewal."""

import logging
import uuid

from auth.oidc_common.renewal import refresh_session
from auth.oidc_common.session import SessionKeys, accept_authority, authority_marker
from simple_module_db import independent_session
from sqlmodel import select

from keycloak.core.constants import (
    SESSION_ID_TOKEN_KEY,
    SESSION_IDENTITY_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_USER_KEY,
)
from keycloak.identity.tokens import open_refresh_token, store_refresh_token
from keycloak.models import KeycloakUserCache

logger = logging.getLogger(__name__)

_KEYS = SessionKeys(
    SESSION_USER_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    "keycloak_refresh_attempted",
    identity=SESSION_IDENTITY_KEY,
    obsolete=(SESSION_ID_TOKEN_KEY,),
)


class SessionRenewal:
    _forget_session = staticmethod(_KEYS.forget)

    @property
    def _session_authority(self) -> str:
        s = self._settings
        issuer = f"{s.server_url.rstrip('/')}/realms/{s.realm}" if s else ""
        return authority_marker(self.name, issuer, s.client_id if s else "")

    def _accept_session(self, session) -> bool:
        return accept_authority(
            session,
            self._session_authority,
            # Pre-#750 Keycloak sessions have no identity key, but their sealed
            # refresh token is Keycloak's own.
            (SESSION_IDENTITY_KEY, SESSION_REFRESH_TOKEN_KEY),
            SESSION_USER_KEY,
        )

    async def _refresh_session(self, request):
        from keycloak.web.endpoints.api import _get_oidc_client

        async def refresh(token):
            return await _get_oidc_client(request).refresh_tokens(token)

        async def validate(tokens):
            return await self.jwks_cache.validate_jwt(tokens.get("access_token", ""))

        async def matches(claims, old_ctx):
            try:
                try:
                    cache_id = uuid.UUID(old_ctx.id)
                except ValueError:
                    # The sign-in upsert fell back to the raw ``sub``.
                    return old_ctx.id == claims["sub"]
                async with independent_session(request.app) as db:
                    subject = (
                        await db.execute(
                            select(KeycloakUserCache.keycloak_sub).where(
                                KeycloakUserCache.id == cache_id
                            )
                        )
                    ).scalar_one_or_none()
                return subject is not None and subject == claims["sub"]
            except Exception as exc:
                # The refresh token is already spent, so signing out here would
                # turn a database blip into a lost sign-in. The token is bound to
                # its user at the IdP; fall back to what origin/main did (no
                # identity check) for this one renewal.
                logger.warning(
                    "Keycloak identity check unavailable during renewal (%s)", type(exc).__name__
                )
                return True

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
