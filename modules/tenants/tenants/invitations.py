"""Invitations: an owner/admin invites an email; that user accepts while signed in.

Provider-agnostic on purpose — no user lookup, no mailer. The raw token is
returned once to the inviter (to copy) and carried on ``InvitationCreated``
(for a mailer module to send); only its SHA-256 is stored.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.constants import MembershipRole, TenantStatus
from tenants.contracts.events import InvitationCreated
from tenants.contracts.schemas import InvitationCreate
from tenants.errors import TenantError
from tenants.models import Invitation, Tenant
from tenants.service import TenantService

ACCEPT_PATH = "/tenants/invitations/accept"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone=True columns.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _pending_clause(tenant_id: str):
    return (
        (Invitation.tenant_id == tenant_id)
        & Invitation.accepted_at.is_(None)
        & (Invitation.expires_at > _now())
    )


async def pending_invitation_count(db: AsyncSession, tenant_id: str) -> int:
    stmt = select(func.count()).select_from(Invitation).where(_pending_clause(tenant_id))
    return int(await db.scalar(stmt) or 0)


class InvitationService:
    def __init__(self, tenants: TenantService, *, ttl_hours: int) -> None:
        self.tenants = tenants
        self.db = tenants.db
        self.ttl = timedelta(hours=ttl_hours)

    async def create(
        self, tenant_id: str, data: InvitationCreate, *, base_url: str
    ) -> tuple[Invitation, str, str]:
        """Return ``(invitation, raw_token, accept_url)``."""
        tenant = await self.tenants.lock(tenant_id)
        if await self.tenants.has_member_email(tenant_id, data.email):
            raise TenantError("already_member", status_code=409)
        duplicate = await self.db.scalar(
            select(Invitation.id).where(_pending_clause(tenant_id), Invitation.email == data.email)
        )
        if duplicate is not None:
            raise TenantError("already_invited", status_code=409)
        await self.tenants.ensure_seat_available(tenant_id)
        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            tenant_id=tenant_id,
            email=data.email,
            role=data.role,
            token_hash=hash_token(token),
            expires_at=_now() + self.ttl,
        )
        self.db.add(invitation)
        await self.db.flush()
        accept_url = f"{base_url.rstrip('/')}{ACCEPT_PATH}?token={token}"
        self.tenants._after_commit(
            InvitationCreated(tenant_id, tenant.name, data.email, data.role, accept_url)
        )
        return invitation, token, accept_url

    async def list_pending(self, tenant_id: str) -> list[Invitation]:
        stmt = select(Invitation).where(_pending_clause(tenant_id)).order_by(Invitation.created_at)
        return list((await self.db.execute(stmt)).scalars().all())

    async def revoke(self, tenant_id: str, invitation_id: int) -> None:
        invitation = await self.db.get(Invitation, invitation_id)
        if invitation is None or invitation.tenant_id != tenant_id:
            raise TenantError("invitation_not_found", status_code=404)
        await self.db.delete(invitation)
        await self.db.flush()

    async def lookup(
        self, token: str, *, for_update: bool = False
    ) -> tuple[Invitation, Tenant] | None:
        if not token:
            return None
        stmt = (
            select(Invitation, Tenant)
            .join(Tenant, Tenant.id == Invitation.tenant_id)
            .where(Invitation.token_hash == hash_token(token))
        )
        if for_update:  # two concurrent accepts of one link must not both pass
            stmt = stmt.with_for_update(of=Invitation)
        row = (await self.db.execute(stmt)).first()
        return (row[0], row[1]) if row else None

    @staticmethod
    def is_expired(invitation: Invitation) -> bool:
        return _aware(invitation.expires_at) <= _now()

    async def accept(self, token: str, *, user_id: str, user_email: str) -> Tenant:
        found = await self.lookup(token, for_update=True)
        if found is None:
            raise TenantError("invitation_not_found", status_code=404)
        invitation, tenant = found
        if invitation.accepted_at is not None:
            raise TenantError("invitation_used", status_code=409)
        if tenant.status != TenantStatus.ACTIVE:
            raise TenantError("tenant_suspended", status_code=409)
        if self.is_expired(invitation):
            raise TenantError("invitation_expired", status_code=410)
        # The link is a bearer secret; binding it to the invited address means
        # a forwarded or leaked link cannot enrol a different account.
        if user_email.strip().lower() != invitation.email:
            raise TenantError("invitation_email_mismatch", status_code=403)
        invitation.accepted_at = _now()
        await self.tenants.add_member(
            tenant.id,
            user_id,
            MembershipRole(invitation.role),
            email=invitation.email,
            seat_reserved=True,
        )
        return tenant
