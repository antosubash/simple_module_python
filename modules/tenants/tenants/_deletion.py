"""Removing a tenant and the rows that only make sense inside it."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.contracts.events import TenantDeleted
from tenants.models import Invitation, Membership, Tenant


async def delete_tenant_rows(db: AsyncSession, tenant: Tenant) -> TenantDeleted:
    """Delete memberships, invitations and the tenant itself, then flush.

    Returns the ``TenantDeleted`` event for the caller to queue on commit.

    Done explicitly rather than leaning on ``ON DELETE CASCADE``, which only
    fires where the database enforces foreign keys.
    """
    for model in (Membership, Invitation):
        await db.execute(delete(model).where(model.tenant_id == tenant.id))
    event = TenantDeleted(tenant.id, tenant.slug, tenant.name)
    await db.delete(tenant)
    await db.flush()
    return event
