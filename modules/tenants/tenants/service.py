"""Tenant and membership business logic.

Every membership operation takes ``tenant_id`` explicitly and filters on it —
these tables are not ``MultiTenantMixin`` (see ``models``), so the scoping the
listener would otherwise add is done here, by hand, in one place.

Side effects (domain events, cache invalidation) run *after commit* through
``_after_commit``: a billing handler must never create a customer for a tenant
whose transaction rolled back.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from simple_module_core.events import Event, EventBus
from simple_module_db import PLATFORM_TENANT_ID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tenants._owner_guard import demote_owner, remove_owner
from tenants.constants import (
    ENTITLEMENT_SEATS,
    MAX_SLUG_LEN,
    MembershipRole,
    TenantStatus,
)
from tenants.contracts.entitlements import (
    EntitlementProvider,
    UnlimitedEntitlements,
    ensure_within_limit,
)
from tenants.contracts.events import (
    MembershipAdded,
    MembershipRemoved,
    TenantCreated,
    TenantStatusChanged,
)
from tenants.contracts.schemas import TenantCreate
from tenants.errors import TenantError
from tenants.models import Membership, Tenant

Invalidate = Callable[[str | None], Awaitable[None]]


async def _no_invalidate(_key: str | None) -> None:
    return None


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:MAX_SLUG_LEN].strip("-") or "org"


class TenantService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        bus: EventBus | None = None,
        invalidate: Invalidate = _no_invalidate,
        entitlements: EntitlementProvider | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self.invalidate = invalidate
        self.entitlements = entitlements or UnlimitedEntitlements()
        self.pending: list[Callable[[], Awaitable[Any]]] = []

    # ── side effects ────────────────────────────────────────────

    def _after_commit(self, *events: Event, invalidate: Sequence[str | None] = ()) -> None:
        async def run() -> None:
            for key in invalidate:
                await self.invalidate(key)
            if self.bus is not None:
                for event in events:
                    await self.bus.publish(event)

        on_commit = getattr(self.db, "on_commit", None)
        if on_commit is not None:
            on_commit(run)
        else:  # plain AsyncSession (scripts, tests): caller drains ``pending``
            self.pending.append(run)

    # ── tenants ─────────────────────────────────────────────────

    async def get(self, tenant_id: str) -> Tenant | None:
        return await self.db.get(Tenant, tenant_id)

    async def _free_slug(self, wanted: str) -> str:
        slug = wanted
        # The reserved platform owner is never handed out, even as a slug.
        while slug == PLATFORM_TENANT_ID or await self.db.scalar(
            select(Tenant.id).where(Tenant.slug == slug)
        ):
            suffix = secrets.token_hex(2)
            slug = f"{wanted[: MAX_SLUG_LEN - len(suffix) - 1]}-{suffix}"
        return slug

    async def create_tenant(
        self, data: TenantCreate, *, owner_user_id: str, owner_email: str | None = None
    ) -> Tenant:
        if data.slug:
            if await self.db.scalar(select(Tenant.id).where(Tenant.slug == data.slug)):
                raise TenantError("slug_taken", status_code=409)
            slug = data.slug
        else:
            slug = await self._free_slug(slugify(data.name))
        tenant = Tenant(name=data.name, slug=slug)
        self.db.add(tenant)
        try:
            # A concurrent create can claim the slug between the check above
            # and this insert: a 409, not a 500. The request fails as a whole,
            # so its transaction is rolled back — no savepoint needed.
            await self.db.flush()
        except IntegrityError as exc:
            raise TenantError("slug_taken", status_code=409) from exc
        owner = Membership(
            tenant_id=tenant.id, user_id=owner_user_id, role=MembershipRole.OWNER, email=owner_email
        )
        self.db.add(owner)
        await self.db.flush()
        self._after_commit(
            TenantCreated(tenant.id, tenant.slug, tenant.name, owner_user_id),
            MembershipAdded(tenant.id, owner_user_id, MembershipRole.OWNER),
            invalidate=[owner_user_id],
        )
        return tenant

    async def set_status(self, tenant_id: str, status: TenantStatus) -> Tenant:
        """Suspend or reactivate — the call a billing module makes on dunning."""
        tenant = await self._require(tenant_id)
        previous = tenant.status
        if previous != status:
            tenant.status = status
            await self.db.flush()
            # Every member's cached view of this tenant is now wrong.
            self._after_commit(TenantStatusChanged(tenant_id, status, previous), invalidate=[None])
        return tenant

    async def list_all(self, *, search: str = "", limit: int = 50, offset: int = 0) -> list[Tenant]:
        stmt = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Tenant.name).like(like) | Tenant.slug.like(like))
        return list((await self.db.execute(stmt)).scalars().all())

    async def member_counts(self, tenant_ids: Sequence[str]) -> dict[str, int]:
        if not tenant_ids:
            return {}
        stmt = (
            select(Membership.tenant_id, func.count())
            .where(Membership.tenant_id.in_(tenant_ids))
            .group_by(Membership.tenant_id)
        )
        return dict((await self.db.execute(stmt)).tuples().all())

    async def lock(self, tenant_id: str) -> Tenant:
        """Row-lock the tenant for the rest of the transaction.

        Serialises check-then-act rules per tenant — "at least one owner",
        "within the seat limit" — so two concurrent requests cannot both pass
        the check and together break the rule. On SQLite ``FOR UPDATE``
        compiles away; there the database's own writer lock serialises the
        two transactions (see ``tests/test_owner_race.py``).
        """
        stmt = select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        tenant = (await self.db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise TenantError("not_found", status_code=404)
        return tenant

    async def _require(self, tenant_id: str) -> Tenant:
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise TenantError("not_found", status_code=404)
        return tenant

    # ── memberships ─────────────────────────────────────────────

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
            Membership.tenant_id == tenant_id, Membership.user_id == user_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_members(self, tenant_id: str) -> list[Membership]:
        stmt = (
            select(Membership)
            .where(Membership.tenant_id == tenant_id)
            .order_by(Membership.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def seats_used(self, tenant_id: str) -> int:
        """Members plus pending invitations — an invite reserves a seat."""
        from tenants.invitations import pending_invitation_count

        members = await self.db.scalar(
            select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant_id)
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
            .where(Membership.tenant_id == tenant_id, Membership.role == MembershipRole.OWNER)
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
