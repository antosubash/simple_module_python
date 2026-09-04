"""KeycloakAuthProvider — resolves users from Keycloak JWTs or session."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from starlette.requests import Request

if TYPE_CHECKING:
    from keycloak.jwks import JWKSCache
    from keycloak.settings import KeycloakSettings

logger = logging.getLogger(__name__)

_SESSION_USER_CTX_KEY = "user_ctx"


class KeycloakAuthProvider:
    """OIDC auth provider backed by Keycloak."""

    name = "keycloak"
    _is_auth_provider = True

    def __init__(self, settings: KeycloakSettings | None = None) -> None:
        self._settings = settings
        self.jwks_cache: JWKSCache | None = None

    async def resolve_user(self, request: Request) -> UserContext | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request, auth_header[7:])

        session = request.scope.get("session", {})
        return UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))

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
            roles=mapped,
            tenant_id=claims.get("tenant_id"),
        )

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
