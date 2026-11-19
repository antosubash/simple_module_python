"""Active tenant and membership lookups without a request or an application."""

from typing import Any

from sqlalchemy import select

from tenants.core.constants import TenantStatus
from tenants.models import Membership, Tenant


async def tenant_active(db: Any, tenant_id: str) -> bool:
    status = await db.scalar(select(Tenant.status).where(Tenant.id == tenant_id))
    return status == TenantStatus.ACTIVE


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
