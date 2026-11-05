"""OidcAuthProvider — resolves users from Oidc JWTs or session."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_BEARER, is_api_token, parse_bearer
from auth.oidc_common.claims import extract_nested as _extract_nested
from auth.oidc_common.tenant import trusted_tenant, without_tenant_roles
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY, session_has_expired
from starlette.requests import Request

from oidc.core.constants import LOGIN_PATH, LOGOUT_PATH, SESSION_USER_KEY
from oidc.identity.persistence import CachePersistence
from oidc.identity.renewal import SessionRenewal

if TYPE_CHECKING:
    from oidc.core.settings import OidcSettings
    from oidc.core.state import OidcState
    from oidc.identity.jwks import JWKSCache

logger = logging.getLogger(__name__)


class IdentityUnavailableError(Exception):
    """The user cache could not record the signed-in identity."""


class OidcAuthProvider(CachePersistence, SessionRenewal):
    """Generic OIDC authentication with issuer-scoped identities."""

    name = "oidc"
    _is_auth_provider = True

    def __init__(
        self, settings: OidcSettings | None = None, *, state: OidcState | None = None
    ) -> None:
        self._initial_settings = settings
        # The module's state object: a settings save or the boot-time DB
        # hydration swaps ``state.settings``, so reading through it keeps
        # ``trust_tenant_claim`` / ``role_mapping`` edits live.
        self._state = state
        self.jwks_cache: JWKSCache | None = None
        self._warned_tenant_roles: set[str] = set()

    @property
    def _settings(self) -> OidcSettings | None:
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
        if type(session.get(SESSION_EXPIRES_AT_KEY)) is not int or session_has_expired(session):
            return await self._refresh_session(request)
        ctx = UserContext.from_session_dict(session.get(SESSION_USER_KEY))
        if ctx is not None:
            # The cookie froze what was decided at login; re-decide with the
            # current settings, so turning trust_tenant_claim off takes effect
            # on sessions that already exist.
            ctx.tenant_id = self._trusted_tenant(ctx.tenant_id)
            ctx.roles = self._without_tenant_roles(ctx.roles)
        return ctx

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return LOGIN_PATH

    def get_logout_url(self, request: Request | None) -> str:
        return LOGOUT_PATH

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return parse_bearer(request.headers.get("authorization")) is not None

    async def _resolve_bearer(self, request: Request, token: str) -> UserContext | None:
        if self.jwks_cache is None or not self._settings or not self._settings.api_audience:
            logger.debug("OIDC bearer authentication unavailable")
            return None
        claims = await self.jwks_cache.validate_jwt(token, audience=self._settings.api_audience)
        if claims is None or not self._allowed_api_client(claims):
            return None

        cache_id = await self._upsert_user_cache(request, claims, throttle_login=True)
        if cache_id is None:
            return None
        ctx = self._claims_to_user_context(claims, cache_id=cache_id)
        # Full rights, but a bearer credential: it may not manage API tokens
        # (``auth.contracts.tokens.AUTH_KIND_BEARER``). The browser sign-in
        # builds the same context from the callback and keeps ``"session"``.
        ctx.auth_kind = AUTH_KIND_BEARER
        return ctx

    def _allowed_api_client(self, claims: dict[str, Any]) -> bool:
        """Whether the client that obtained this API token may call us.

        Fails closed: a token naming no client (no ``azp``/``appid``) is refused.
        """
        s = self._settings
        client = claims.get("azp") or claims.get("appid")
        if not isinstance(client, str) or not client or not s:
            return False
        if client == s.client_id or client in s.api_allowed_client_ids:
            return True
        logger.info("OIDC bearer token from a client not in api_allowed_client_ids")
        return False

    async def sign_in_from_claims(
        self, request: Request, claims: dict[str, Any]
    ) -> tuple[UserContext, tuple[str, str]]:
        """Turn verified ID-token claims into a browser sign-in.

        Returns the session ``UserContext`` and the ``(issuer, subject)``
        identity to pin the session to. The caller has already validated the
        token, nonce and expiry. Raises ``ValueError`` when the claims carry no
        usable identity and ``IdentityUnavailableError`` when the user cache
        refuses it.
        """
        identity = self._identity(claims)
        cache_id = await self._upsert_user_cache(request, claims)
        if cache_id is None:
            raise IdentityUnavailableError("OIDC identity unavailable")
        return self._claims_to_user_context(claims, cache_id=cache_id), identity

    def _claims_to_user_context(
        self,
        claims: dict[str, Any],
        *,
        cache_id: str,
    ) -> UserContext:
        s = self._settings
        roles_raw = _extract_nested(claims, s.roles_claim_path) if s else None
        mapping = s.role_mapping if s else {}
        mapped = [mapping[r] for r in (roles_raw or []) if isinstance(r, str) and r in mapping]
        return UserContext(
            id=cache_id,
            email=self._email(claims) or "",
            email_verified=bool(
                (not s or s.provider != "entra") and claims.get("email_verified") is True
            ),
            name=self._display_name(claims),
            roles=self._without_tenant_roles(mapped),
            tenant_id=self._trusted_tenant(claims.get("tenant_id")),
        )

    def _email(self, claims: dict[str, Any]) -> str | None:
        """The configured email claim, or ``None`` when absent or not a string."""
        value = claims.get(self._settings.email_claim if self._settings else "email")
        return value if isinstance(value, str) else None

    def _display_name(self, claims: dict[str, Any]) -> str:
        s = self._settings
        for name in (
            s.username_claim if s else "preferred_username",
            s.name_claim if s else "name",
        ):
            value = claims.get(name)
            if isinstance(value, str) and value:
                return value
        return ""

    def _subject(self, claims: dict[str, Any]) -> str:
        key = self._settings.uid_claim if self._settings else "sub"
        subject = claims.get(key)
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Missing configured OIDC identity claim")
        return subject

    def _identity(self, claims: dict[str, Any]) -> tuple[str, str]:
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("Missing OIDC issuer")
        return issuer, self._subject(claims)

    def _trusted_tenant(self, value: Any) -> str | None:
        return trusted_tenant(
            value, trust_claim=bool(self._settings and self._settings.trust_tenant_claim)
        )

    def _without_tenant_roles(self, roles: list[str]) -> list[str]:
        return without_tenant_roles(roles, warned=self._warned_tenant_roles, provider="Oidc")
