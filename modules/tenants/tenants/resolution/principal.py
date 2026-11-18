"""The active membership role, usable without a request or an application."""

from typing import Any

from sqlalchemy import select

from tenants.core.constants import TenantStatus
from tenants.models import Membership, Tenant


async def membership_role(db: Any, user_id: str, tenant_id: str) -> str | None:
    result = await db.execute(
        select(Membership.role)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Tenant.status == TenantStatus.ACTIVE,
        )
    )
    return result.scalar_one_or_none()
