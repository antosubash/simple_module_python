"""Remove a deleted principal from every organisation (#627)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.durable_events import DurableContext
from simple_module_db.callbacks import register_on_commit
from sqlmodel import col, delete, select

from tenants.constants import MembershipRole, TenantStatus
from tenants.models import Membership, Tenant
from tenants.resolver import forget

if TYPE_CHECKING:
    from simple_module_core.user_events import UserDeleted


async def purge_user_memberships(event: UserDeleted, ctx: DurableContext) -> None:
    user_id = str(event.user_id)
    # Use the same tenant locks as membership edits; lock in a stable order.
    owned = select(Membership.tenant_id).where(
        col(Membership.user_id) == user_id, Membership.role == MembershipRole.OWNER
    )
    stmt = select(Tenant).where(col(Tenant.id).in_(owned)).order_by(Tenant.id).with_for_update()
    tenants = (await ctx.db.scalars(stmt)).all()
    await ctx.db.execute(delete(Membership).where(col(Membership.user_id) == user_id))
    for tenant in tenants:
        owner = await ctx.db.scalar(
            select(Membership.id)
            .where(Membership.tenant_id == tenant.id, Membership.role == MembershipRole.OWNER)
            .limit(1)
        )
        if owner is None:
            # Flag the orphan for platform administration without granting ownership.
            tenant.status = TenantStatus.SUSPENDED
    await ctx.db.flush()
    register_on_commit(ctx.db, lambda: forget(None))
