"""OIDC identity-token adapter for shared browser renewal."""

from auth.oidc_common.renewal import refresh_session
from auth.oidc_common.session import SessionKeys, accept_authority, authority_marker

from oidc.constants import (
    SESSION_IDENTITY_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_USER_KEY,
)
from oidc.runtime import require_client
from oidc.tokens import open_refresh_token, store_refresh_token

_KEYS = SessionKeys(
    SESSION_USER_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_REFRESH_RETRY_AT_KEY,
    "oidc_refresh_attempted",
    identity=SESSION_IDENTITY_KEY,
)


class SessionRenewal:
    _forget_session = staticmethod(_KEYS.forget)

    @property
    def _session_authority(self) -> str:
        s = self._settings
        issuer = s.discovery_url.replace("/.well-known/openid-configuration", "", 1) if s else ""
        return authority_marker(self.name, issuer, s.client_id if s else "")

    def _accept_session(self, session) -> bool:
        return accept_authority(
            session,
            self._session_authority,
            (SESSION_IDENTITY_KEY,),
            SESSION_USER_KEY,
            legacy_ok=lambda: self._legacy_identity_matches(session),
        )

    def _legacy_identity_matches(self, session) -> bool:
        identity = session.get(SESSION_IDENTITY_KEY)
        if (
            not isinstance(identity, list)
            or len(identity) != 2
            or not self.jwks_cache
            or not self._settings
        ):
            return False
        issuer = self.jwks_cache.issuer
        configured = self._settings.discovery_url.replace(
            "/.well-known/openid-configuration", "", 1
        )
        # Discovery tolerates a trailing slash; token issuers must match exactly.
        return issuer.rstrip("/") == configured.rstrip("/") and identity[0] == issuer

    async def _refresh_session(self, request):
        async def refresh(token):
            return await (await require_client(request)).refresh_tokens(token)

        async def validate(tokens):
            return await self.jwks_cache.validate_jwt(
                tokens.get("id_token", ""), audience=self._settings.client_id
            )

        async def matches(claims, old_ctx):
            try:
                return list(self._identity(claims)) == request.session.get(SESSION_IDENTITY_KEY)
            except ValueError:
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
