"""OidcAuthProvider — resolves users from OIDC tokens or session."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from starlette.requests import Request

if TYPE_CHECKING:
    from oidc.jwks import JWKSCache
    from oidc.settings import OidcSettings

logger = logging.getLogger(__name__)

_SESSION_USER_CTX_KEY = "user_ctx"


class OidcAuthProvider:
    """Generic OIDC auth provider (Entra, Auth0, Okta, ...)."""

    name = "oidc"
    _is_auth_provider = True

    def __init__(self, settings: OidcSettings | None = None) -> None:
        self._settings = settings
        self.jwks_cache: JWKSCache | None = None

    async def resolve_user(self, request: Request) -> UserContext | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request, auth_header[7:])

        session = request.scope.get("session", {})
        return UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return "/oidc/login"

    def get_logout_url(self, request: Request | None) -> str:
        return "/oidc/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            ("/oidc/login", "/oidc/logout", "/api/oidc/auth/"),
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

    def _subject(self, claims: dict[str, Any]) -> str:
        """Stable subject id: the configured uid claim, falling back to ``sub``."""
        uid_claim = self._settings.uid_claim if self._settings else "sub"
        return str(claims.get(uid_claim) or claims.get("sub") or "")

    def _claims_to_user_context(
        self,
        claims: dict[str, Any],
        *,
        cache_id: str,
    ) -> UserContext:
        s = self._settings
        roles_raw = (
            _extract_nested(claims, s.roles_claim_path) if s and s.roles_claim_path else None
        )
        mapping = s.role_mapping if s else {}
        mapped = [mapping[r] for r in (roles_raw or []) if r in mapping]
        username = claims.get(s.username_claim) if s else None
        return UserContext(
            id=cache_id,
            email=claims.get(s.email_claim, "") if s else claims.get("email", ""),
            name=(username or (claims.get(s.name_claim, "") if s else claims.get("name", ""))),
            roles=mapped,
            tenant_id=claims.get("tid") or claims.get("tenant_id"),
        )

    async def _upsert_user_cache(self, request: Request, claims: dict) -> str:
        subject = self._subject(claims)
        try:
            from sqlalchemy import select

            from oidc.models import OidcUserCache

            session_factory = request.app.state.sm.db.session_factory
            async with session_factory() as db:
                stmt = select(OidcUserCache).where(OidcUserCache.subject == subject)
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row is None:
                    row = self._new_cache_row(subject, claims)
                    db.add(row)
                else:
                    self._touch_cache_row(row, claims)
                await db.flush()
                row_id = str(row.id)
                # This is a self-managed session (not the request-scoped
                # ``get_db``), so it must commit explicitly — otherwise the row
                # is rolled back on close and the subject->UUID mapping never
                # persists, minting a fresh id on every login.
                await db.commit()
                return row_id
        except Exception:
            logger.exception("Failed to upsert OidcUserCache for subject=%s", subject)
            return subject or "unknown"

    def _full_name(self, claims: dict) -> str | None:
        s = self._settings
        if s:
            return claims.get(s.username_claim) or claims.get(s.name_claim)
        return claims.get("name")

    def _new_cache_row(self, subject: str, claims: dict):
        import uuid as uuid_mod
        from datetime import datetime

        from oidc.models import OidcUserCache

        email_claim = self._settings.email_claim if self._settings else "email"
        return OidcUserCache(
            id=uuid_mod.uuid4(),
            subject=subject,
            email=claims.get(email_claim, ""),
            full_name=self._full_name(claims),
            last_login_at=datetime.now(UTC),
        )

    def _touch_cache_row(self, row, claims: dict) -> None:
        from datetime import datetime

        email_claim = self._settings.email_claim if self._settings else "email"
        row.email = claims.get(email_claim, row.email)
        row.full_name = self._full_name(claims) or row.full_name
        row.last_login_at = datetime.now(UTC)


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
