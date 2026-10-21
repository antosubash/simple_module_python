"""Creating, listing and revoking API tokens.

Authorisation decisions — who may create what, which scopes a creator may
hand out — are made by the caller (``api_tokens.scopes`` and the endpoints);
this layer enforces only the invariants every token must satisfy wherever it
came from: a non-empty scope list, no ``admin`` role on a service key, an
expiry within ``max_lifetime_days``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from simple_module_core.user_directory import NullUserDirectory, UserDirectory
from simple_module_db import ALL_TENANTS_OPTION, all_tenants
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_tokens.constants import FORBIDDEN_SERVICE_ROLES, TokenKind
from api_tokens.contracts.schemas import TokenView
from api_tokens.models import ApiToken
from api_tokens.tokens import generate


class TokenError(Exception):
    """A request the service refuses. ``key`` is an ``api_tokens.errors.*`` key."""

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key = key
        self.params = params


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApiTokenService:
    def __init__(self, db: AsyncSession, directory: UserDirectory | None = None) -> None:
        self.db = db
        # Owners are read through the app's user directory (GH #501); without
        # one, nobody has a usable account and owners show unnamed.
        self.directory: UserDirectory = directory or NullUserDirectory()

    async def create(
        self,
        *,
        kind: TokenKind,
        name: str,
        scopes: Sequence[str],
        expires_in_days: int,
        max_lifetime_days: int,
        owner_user_id: uuid.UUID | None = None,
        roles: Sequence[str] = (),
    ) -> tuple[ApiToken, str]:
        """Persist a new token; return it with its plaintext (shown once)."""
        if not scopes:
            raise TokenError("api_tokens.errors.scopes_required")
        if not 1 <= expires_in_days <= max_lifetime_days:
            raise TokenError("api_tokens.errors.lifetime_too_long", days=max_lifetime_days)
        if kind is TokenKind.PERSONAL:
            if owner_user_id is None or roles:
                raise TokenError("api_tokens.errors.invalid_kind")
        elif owner_user_id is not None:
            raise TokenError("api_tokens.errors.invalid_kind")
        forbidden = sorted(set(roles) & FORBIDDEN_SERVICE_ROLES)
        if forbidden:
            raise TokenError("api_tokens.errors.role_forbidden", role=forbidden[0])

        new = generate(kind)
        token = ApiToken(
            kind=kind,
            name=name,
            prefix=new.prefix,
            token_hash=new.token_hash,
            owner_user_id=owner_user_id,
            scopes=sorted(set(scopes)),
            roles=sorted(set(roles)),
            expires_at=_utcnow() + timedelta(days=expires_in_days),
        )
        self.db.add(token)
        await self.db.flush()
        return token, new.plaintext

    async def has_usable_account(self, user_id: uuid.UUID) -> bool:
        """Whether *user_id* is an active account the resolver can turn into a principal.

        That takes a directory entry that is active **and** whose roles are
        known: under a provider that keeps roles in the IdP (Keycloak), a token
        minted for the id would be dead on arrival, since the resolver refuses
        a personal token whose owner's roles it cannot read.
        """
        found = await self.directory.get_many(self.db, [str(user_id)], with_roles=True)
        owner = found.get(str(user_id))
        return owner is not None and owner.is_active and owner.roles is not None

    async def revoke_all_for_owner(self, owner_user_id: uuid.UUID) -> int:
        """Revoke every live personal token *owner_user_id* holds, in any tenant."""
        tokens = [t for t in await self.list_for_owner(owner_user_id) if t.revoked_at is None]
        now = _utcnow()
        for token in tokens:
            token.revoked_at = now
        if tokens:
            with all_tenants():
                await self.db.flush()
        return len(tokens)

    async def list_for_owner(self, owner_user_id: uuid.UUID) -> list[ApiToken]:
        """Every personal token *owner_user_id* holds, in any tenant.

        Across tenants on purpose: a token is its owner's, and one created
        while another organisation was active must still be listable — and
        revocable — from wherever the owner is now.
        """
        stmt = (
            select(ApiToken)
            .where(ApiToken.owner_user_id == owner_user_id, ApiToken.kind == TokenKind.PERSONAL)  # ty: ignore[invalid-argument-type]
            .order_by(ApiToken.created_at.desc())
            .execution_options(**{ALL_TENANTS_OPTION: True})
        )
        return list((await self.db.execute(stmt)).scalars())

    async def list_tenant(self) -> list[ApiToken]:
        """Every token in the active tenant (tenant-filtered, fail-closed)."""
        stmt = select(ApiToken).order_by(ApiToken.created_at.desc())
        return list((await self.db.execute(stmt)).scalars())

    async def get_owned(self, token_id: uuid.UUID, owner_user_id: uuid.UUID) -> ApiToken | None:
        stmt = (
            select(ApiToken)
            .where(
                ApiToken.id == token_id,  # ty: ignore[invalid-argument-type]
                ApiToken.owner_user_id == owner_user_id,  # ty: ignore[invalid-argument-type]
                ApiToken.kind == TokenKind.PERSONAL,  # ty: ignore[invalid-argument-type]
            )
            .execution_options(**{ALL_TENANTS_OPTION: True})
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_in_tenant(self, token_id: uuid.UUID) -> ApiToken | None:
        stmt = select(ApiToken).where(ApiToken.id == token_id)  # ty: ignore[invalid-argument-type]
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: ApiToken, *, cross_tenant: bool = False) -> ApiToken:
        """Mark *token* revoked. Idempotent: a second revoke keeps the first time.

        ``cross_tenant`` is for an owner revoking their own token from another
        tenant; the flush runs inside ``all_tenants()`` so the tenant guard
        lets the row be written. Flushed here, not at commit, for that reason.
        """
        if token.revoked_at is None:
            token.revoked_at = _utcnow()
            if cross_tenant:
                with all_tenants():
                    await self.db.flush()
            else:
                await self.db.flush()
        return token

    async def owner_emails(self, tokens: Sequence[ApiToken]) -> dict[uuid.UUID, str]:
        ids = {t.owner_user_id for t in tokens if t.owner_user_id is not None}
        if not ids:
            return {}
        found = await self.directory.get_many(self.db, [str(i) for i in ids])
        return {i: found[str(i)].email for i in ids if str(i) in found}

    @staticmethod
    def to_view(token: ApiToken, owner_email: str | None = None) -> TokenView:
        view = TokenView.model_validate(token)
        view.owner_email = owner_email
        return view


__all__ = ["ApiTokenService", "TokenError"]
