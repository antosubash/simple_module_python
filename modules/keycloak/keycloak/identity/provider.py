"""KeycloakAuthProvider — resolves users from Keycloak JWTs or session."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_BEARER, is_api_token, parse_bearer
from auth.oidc_common.claims import extract_nested as _extract_nested
from auth.oidc_common.tenant import trusted_tenant, without_tenant_roles
from simple_module_hosting.session import session_has_expired
from starlette.requests import Request

from keycloak.core.constants import SESSION_USER_KEY as _SESSION_USER_CTX_KEY
from keycloak.identity.persistence import CachePersistence
from keycloak.identity.renewal import SessionRenewal

if TYPE_CHECKING:
    from keycloak.core.settings import KeycloakSettings
    from keycloak.core.state import KeycloakState
    from keycloak.identity.jwks import JWKSCache

logger = logging.getLogger(__name__)


class KeycloakAuthProvider(CachePersistence, SessionRenewal):
    """OIDC auth provider backed by Keycloak."""

    name = "keycloak"
    _is_auth_provider = True

    def __init__(
        self, settings: KeycloakSettings | None = None, *, state: KeycloakState | None = None
    ) -> None:
        self._initial_settings = settings
        # The module's state object: a settings save or the boot-time DB
        # hydration swaps ``state.settings``, so reading through it keeps
        # ``trust_tenant_claim`` / ``role_mapping`` edits live.
        self._state = state
        self.jwks_cache: JWKSCache | None = None
        self._warned_tenant_roles: set[str] = set()

    @property
    def _settings(self) -> KeycloakSettings | None:
        live = getattr(self._state, "settings", None)
        return live if live is not None else self._initial_settings

    async def resolve_user(self, request: Request) -> UserContext | None:
        credential = parse_bearer(request.headers.get("authorization"))
        if credential is not None:
            # An ``api_tokens`` credential is not a JWT: skip the parse and
            # leave it to the principal resolver that owns it.
            if is_api_token(credential):
                return None
            return await self._resolve_bearer(request, credential)

        session = request.scope.get("session", {})
        if not self._accept_session(session):
            return None
        # Renew authority from the IdP at expiry, without interrupting the request.
        if session_has_expired(session):
            return await self._refresh_session(request)
        ctx = UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))
        if ctx is not None:
            # The cookie froze what was decided at login; re-decide with the
            # current settings, so turning trust_tenant_claim off takes effect
            # on sessions that already exist.
            ctx.tenant_id = self._trusted_tenant(ctx.tenant_id)
            ctx.roles = self._without_tenant_roles(ctx.roles)
        return ctx

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return "/keycloak/login"

    def get_logout_url(self, request: Request | None) -> str:
        return "/keycloak/logout"

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return parse_bearer(request.headers.get("authorization")) is not None

    async def _resolve_bearer(self, request: Request, token: str) -> UserContext | None:
        if self.jwks_cache is None:
            logger.warning("JWKS cache not initialized; rejecting bearer token")
            return None
        claims = await self.jwks_cache.validate_jwt(token)
        if claims is None:
            return None

        cache_id = await self._upsert_user_cache(request, claims, throttle_login=True)
        ctx = self._claims_to_user_context(claims, cache_id=cache_id)
        # Full rights, but a bearer credential: it may not manage API tokens
        # (``auth.contracts.tokens.AUTH_KIND_BEARER``). The browser sign-in
        # builds the same context from the callback and keeps ``"session"``.
        ctx.auth_kind = AUTH_KIND_BEARER
        return ctx

    async def sign_in_from_claims(self, request: Request, claims: dict[str, Any]) -> UserContext:
        """Turn verified access-token claims into the session ``UserContext``.

        The caller has already validated the tokens, nonce and expiry.
        """
        cache_id = await self._upsert_user_cache(request, claims)
        return self._claims_to_user_context(claims, cache_id=cache_id)

    def _claims_to_user_context(
        self,
        claims: dict[str, Any],
        *,
        cache_id: str,
    ) -> UserContext:
        roles_raw = (
            _extract_nested(claims, self._settings.roles_claim_path) if self._settings else None
        )
        mapped = [
            self._settings.role_mapping[r]
            for r in (roles_raw or [])
            if self._settings and isinstance(r, str) and r in self._settings.role_mapping
        ]
        return UserContext(
            id=cache_id,
            email=claims.get("email", ""),
            email_verified=claims.get("email_verified") is True,
            name=(claims.get("preferred_username") or claims.get("name", "")),
            roles=self._without_tenant_roles(mapped),
            tenant_id=self._trusted_tenant(claims.get("tenant_id")),
        )

    def _trusted_tenant(self, value: Any) -> str | None:
        return trusted_tenant(
            value, trust_claim=bool(self._settings and self._settings.trust_tenant_claim)
        )

    def _without_tenant_roles(self, roles: list[str]) -> list[str]:
        return without_tenant_roles(roles, warned=self._warned_tenant_roles, provider="Keycloak")
