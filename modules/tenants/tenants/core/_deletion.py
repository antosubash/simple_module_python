"""Removing a tenant and the rows that only make sense inside it."""

from __future__ import annotations

from simple_module_core.events import Event
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from tenants.contracts.events import MembershipRemoved, TenantDeleted
from tenants.models import Invitation, Membership, Tenant


async def delete_tenant_rows(db: AsyncSession, tenant: Tenant) -> list[Event]:
    """Delete memberships, invitations and the tenant itself, then flush.

    Returns the events for the caller to queue on commit: one
    ``MembershipRemoved`` per member — the same event a single removal
    publishes, so seat counts and per-user state follow — then ``TenantDeleted``.

    Done explicitly rather than leaning on ``ON DELETE CASCADE``, which only
    fires where the database enforces foreign keys.
    """
    user_ids = (
        await db.scalars(
            select(Membership.user_id)
            .where(Membership.tenant_id == tenant.id)
            .order_by(Membership.user_id)
        )
    ).all()
    for model in (Membership, Invitation):
        await db.execute(delete(model).where(col(model.tenant_id) == tenant.id))
    events: list[Event] = [MembershipRemoved(tenant.id, user_id) for user_id in user_ids]
    events.append(TenantDeleted(tenant.id, tenant.slug, tenant.name))
    await db.delete(tenant)
    await db.flush()
    return events
