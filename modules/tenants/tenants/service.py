"""Tenant and membership business logic.

Membership operations filter explicitly on ``tenant_id``: these registry
tables are not ``MultiTenantMixin`` (see ``models``), so scoping is done here.

Side effects (domain events, cache invalidation) run *after commit* through
``_after_commit``: a billing handler must never create a customer for a tenant
whose transaction rolled back.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from simple_module_core.events import Event, EventBus
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.tenant_events import TENANT_DELETED_CHANNEL
from simple_module_db import PLATFORM_TENANT_ID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from tenants._deletion import delete_tenant_rows
from tenants._membership_ops import MembershipOpsMixin
from tenants.constants import MAX_SLUG_LEN, MembershipRole, TenantStatus
from tenants.contracts.entitlements import (
    EntitlementProvider,
    UnlimitedEntitlements,
)
from tenants.contracts.events import (
    MembershipAdded,
    TenantCreated,
    TenantDeleted,
    TenantStatusChanged,
)
from tenants.contracts.schemas import TenantCreate
from tenants.errors import TenantError
from tenants.models import Membership, Tenant

logger = logging.getLogger(__name__)

Invalidate = Callable[[str | None], Awaitable[None]]


async def _no_invalidate(_key: str | None) -> None:
    return None


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:MAX_SLUG_LEN].strip("-") or "org"


class TenantService(MembershipOpsMixin):
    def __init__(
        self,
        db: AsyncSession,
        *,
        bus: EventBus | None = None,
        invalidate: Invalidate = _no_invalidate,
        entitlements: EntitlementProvider | None = None,
        invalidation_bus: InvalidationBus | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self.invalidate = invalidate
        self.invalidation_bus = invalidation_bus
        self.entitlements = entitlements or UnlimitedEntitlements()
        self.pending: list[Callable[[], Awaitable[Any]]] = []

    def _after_commit(
        self,
        *events: Event,
        invalidate: Sequence[str | None] = (),
        callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        async def run() -> None:
            for key in invalidate:
                await self.invalidate(key)
            if self.bus is not None:
                for event in events:
                    await self.bus.publish(event)
            if callback is not None:  # last: may wait on an SMTP server
                await callback()

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

    async def delete_tenant(self, tenant_id: str) -> None:
        tenant = await self.lock(tenant_id)
        events = await delete_tenant_rows(self.db, tenant)
        deleted = next(event for event in events if isinstance(event, TenantDeleted))
        if self.bus is not None:
            await self.bus.publish_durable_or_inline(deleted, self.db)
        else:
            logger.warning(
                "Tenant-owned data cleanup was skipped tenant=%s: no event bus", tenant_id
            )

        async def invalidate_deleted() -> None:
            if self.invalidation_bus is not None:
                await self.invalidation_bus.publish(TENANT_DELETED_CHANNEL, key=tenant_id)

        self._after_commit(*events, invalidate=[None], callback=invalidate_deleted)

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
        stmt = select(Tenant).where(col(Tenant.id) == tenant_id).with_for_update()
        tenant = (await self.db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise TenantError("not_found", status_code=404)
        return tenant

    async def _require(self, tenant_id: str) -> Tenant:
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise TenantError("not_found", status_code=404)
        return tenant
