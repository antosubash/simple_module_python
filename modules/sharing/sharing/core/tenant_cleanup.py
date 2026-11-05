"""Durable teardown of tenant-owned sharing rows."""

from simple_module_core.durable_events import DurableContext
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db.tenancy import tenant_context
from sqlmodel import delete

from sharing.models import ResourceShare


async def purge_tenant_data(event: TenantDeleted, ctx: DurableContext) -> None:
    """Hard-delete tenant rows atomically with outbox acknowledgement."""
    with tenant_context(event.tenant_id):
        await ctx.db.execute(
            delete(ResourceShare).where(ResourceShare.tenant_id == event.tenant_id)
        )
