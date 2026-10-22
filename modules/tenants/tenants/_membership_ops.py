"""Membership operations of :class:`tenants.service.TenantService`.

Split out of ``service`` by responsibility: tenant lifecycle stays there, the
member roster, seats and role changes live here as a mixin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from simple_module_core.events import Event
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tenants._owner_guard import demote_owner, remove_owner
from tenants.constants import ENTITLEMENT_SEATS, MembershipRole
from tenants.contracts.entitlements import EntitlementProvider, ensure_within_limit
from tenants.contracts.events import MembershipAdded, MembershipRemoved
from tenants.errors import TenantError
from tenants.models import Membership, Tenant


class MembershipOpsMixin:
    if TYPE_CHECKING:
        db: AsyncSession
        entitlements: EntitlementProvider

        def _after_commit(
            self,
            *events: Event,
            invalidate: Sequence[str | None] = (),
            callback: Callable[[], Awaitable[None]] | None = None,
        ) -> None: ...
        async def lock(self, tenant_id: str) -> Tenant: ...
        async def _require(self, tenant_id: str) -> Tenant: ...

    async def list_for_user(self, user_id: str) -> list[tuple[Tenant, str]]:
        stmt = (
            select(Tenant, Membership.role)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at, Tenant.name)
        )
        return [(t, role) for t, role in (await self.db.execute(stmt)).all()]

    async def has_member_email(self, tenant_id: str, email: str) -> bool:
        stmt = select(Membership.id).where(
            Membership.tenant_id == tenant_id, func.lower(Membership.email) == email.lower()
        )
        return await self.db.scalar(stmt) is not None

    async def get_membership(self, tenant_id: str, user_id: str) -> Membership | None:
        stmt = select(Membership).where(
            Membership.tenant_id == tenant_id,  # ty: ignore[invalid-argument-type]
            Membership.user_id == user_id,  # ty: ignore[invalid-argument-type]
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_members(self, tenant_id: str) -> list[Membership]:
        stmt = (
            select(Membership)
            .where(Membership.tenant_id == tenant_id)  # ty: ignore[invalid-argument-type]
            .order_by(Membership.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def seats_used(self, tenant_id: str) -> int:
        """Members plus pending invitations — an invite reserves a seat."""
        from tenants.invitations import pending_invitation_count

        members = await self.db.scalar(
            select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant_id)  # ty: ignore[invalid-argument-type]
        )
        return int(members or 0) + await pending_invitation_count(self.db, tenant_id)

    async def ensure_seat_available(self, tenant_id: str) -> None:
        await self.lock(tenant_id)
        used = await self.seats_used(tenant_id)
        await ensure_within_limit(self.entitlements, tenant_id, ENTITLEMENT_SEATS, used)

    async def add_member(
        self,
        tenant_id: str,
        user_id: str,
        role: MembershipRole,
        *,
        email: str | None = None,
        seat_reserved: bool = False,
    ) -> Membership:
        """Add ``user_id``. ``seat_reserved``: the seat was held by an invitation."""
        await self._require(tenant_id)
        existing = await self.get_membership(tenant_id, user_id)
        if existing is not None:
            return existing
        if not seat_reserved:
            await self.ensure_seat_available(tenant_id)
        membership = Membership(tenant_id=tenant_id, user_id=user_id, role=role, email=email)
        self.db.add(membership)
        try:
            await self.db.flush()  # a concurrent join of the same user loses here
        except IntegrityError as exc:
            raise TenantError("already_member", status_code=409) from exc
        self._after_commit(MembershipAdded(tenant_id, user_id, role), invalidate=[user_id])
        return membership

    async def _owner_count(self, tenant_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == tenant_id, Membership.role == MembershipRole.OWNER)  # ty: ignore[invalid-argument-type]
        )
        return int(await self.db.scalar(stmt) or 0)

    async def change_role(
        self, tenant_id: str, user_id: str, role: MembershipRole, *, actor_role: str
    ) -> Membership:
        await self.lock(tenant_id)
        membership = await self.get_membership(tenant_id, user_id)
        if membership is None:
            raise TenantError("member_not_found", status_code=404)
        touches_owner = MembershipRole.OWNER in (role, membership.role)
        if touches_owner and actor_role != MembershipRole.OWNER:
            raise TenantError("owner_required", status_code=403)
        demotes_owner = membership.role == MembershipRole.OWNER and role != MembershipRole.OWNER
        if demotes_owner:
            if not await demote_owner(self.db, membership, role):
                raise TenantError("last_owner", status_code=409)
        else:
            membership.role = role
            await self.db.flush()
        self._after_commit(invalidate=[user_id])
        return membership

    async def remove_member(self, tenant_id: str, user_id: str, *, actor_role: str) -> None:
        await self.lock(tenant_id)
        membership = await self.get_membership(tenant_id, user_id)
        if membership is None:
            raise TenantError("member_not_found", status_code=404)
        if membership.role == MembershipRole.OWNER:
            if actor_role != MembershipRole.OWNER:
                raise TenantError("owner_required", status_code=403)
            if not await remove_owner(self.db, membership):
                raise TenantError("last_owner", status_code=409)
        else:
            await self.db.delete(membership)
            await self.db.flush()
        self._after_commit(MembershipRemoved(tenant_id, user_id), invalidate=[user_id])
