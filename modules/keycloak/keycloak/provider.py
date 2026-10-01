"""KeycloakAuthProvider — resolves users from Keycloak JWTs or session."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from simple_module_core.tenancy import is_tenant_role
from simple_module_db import is_valid_tenant_id
from starlette.requests import Request

if TYPE_CHECKING:
    from keycloak.jwks import JWKSCache
    from keycloak.settings import KeycloakSettings
    from keycloak.state import KeycloakState

logger = logging.getLogger(__name__)

_SESSION_USER_CTX_KEY = "user_ctx"


class KeycloakAuthProvider:
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
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request, auth_header[7:])

        session = request.scope.get("session", {})
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

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            (
                "/keycloak/login",
                "/keycloak/logout",
                # Where the end-session redirect lands: there is no session
                # left to check, and bouncing it to /keycloak/login would sign
                # the visitor straight back in.
                "/keycloak/logged-out",
                "/api/keycloak/auth/",
            ),
            (),
        )

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return request.headers.get("authorization", "").startswith("Bearer ")

    async def _resolve_bearer(self, request: Request, token: str) -> UserContext | None:
        if self.jwks_cache is None:
            logger.warning("JWKS cache not initialized; rejecting bearer token")
            return None
        claims = await self.jwks_cache.validate_jwt(token)
        if claims is None:
            return None

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
            if self._settings and r in self._settings.role_mapping
        ]
        return UserContext(
            id=cache_id,
            email=claims.get("email", ""),
            name=(claims.get("preferred_username") or claims.get("name", "")),
            roles=self._without_tenant_roles(mapped),
            tenant_id=self._trusted_tenant(claims.get("tenant_id")),
        )

    def _trusted_tenant(self, value: Any) -> str | None:
        """The ``tenant_id`` claim, if the operator trusts it and it is well-formed.

        The claim is the IdP's word, not ours: it is ignored unless the operator
        vouches for the realm mapper (``trust_tenant_claim``), and even then a
        registered tenant resolver overrides it every request. It must also pass
        the same id check as any other tenant id taken from outside.
        """
        if value is None or not (self._settings and self._settings.trust_tenant_claim):
            return None
        if not is_valid_tenant_id(value):
            logger.warning("Ignoring malformed tenant_id claim %r", value)
            return None
        return value

    def _without_tenant_roles(self, roles: list[str]) -> list[str]:
        """Drop ``tenant:*`` roles: only the tenants module may grant them, for
        the active tenant. A ``role_mapping`` entry producing one would
        otherwise hand every user that tenant role in every tenant."""
        kept = []
        for role in roles:
            if not is_tenant_role(role):
                kept.append(role)
            elif role not in self._warned_tenant_roles:
                self._warned_tenant_roles.add(role)
                logger.warning(
                    "Keycloak role_mapping produced tenant role %r; ignored "
                    "(tenant roles come from memberships only)",
                    role,
                )
        return kept

    async def _upsert_user_cache(self, request: Request, claims: dict) -> str:
        try:
            from sqlalchemy import select

            from keycloak.models import KeycloakUserCache

            session_factory = request.app.state.sm.db.session_factory
            sub = claims["sub"]
            async with session_factory() as db:
                stmt = select(KeycloakUserCache).where(KeycloakUserCache.keycloak_sub == sub)
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row is None:
                    import uuid as uuid_mod
                    from datetime import datetime

                    row = KeycloakUserCache(
                        id=uuid_mod.uuid4(),
                        keycloak_sub=sub,
                        email=claims.get("email", ""),
                        full_name=claims.get("preferred_username"),
                        last_login_at=datetime.now(UTC),
                    )
                    db.add(row)
                    await db.flush()
                else:
                    from datetime import datetime

                    row.email = claims.get("email", row.email)
                    row.full_name = claims.get("preferred_username", row.full_name)
                    row.last_login_at = datetime.now(UTC)
                    await db.flush()
                return str(row.id)
        except Exception:
            logger.exception(
                "Failed to upsert KeycloakUserCache for sub=%s",
                claims.get("sub"),
            )
            return claims.get("sub", "unknown")


def _extract_nested(data: dict, path: str) -> list[str] | None:
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current if isinstance(current, list) else None
