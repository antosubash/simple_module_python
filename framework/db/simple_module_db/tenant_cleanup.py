"""Durable teardown of framework-owned tenant settings, including branding."""

from simple_module_core.durable_events import DurableContext
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from sqlmodel import col, delete

from simple_module_db.stored_settings import SCOPE_TENANT, Setting


def register_tenant_cleanup(bus: EventBus) -> None:
    """Register in both the host and workers, even without the settings plugin."""
    bus.subscribe_durable(TenantDeleted, delete_tenant_settings)


async def delete_tenant_settings(event: TenantDeleted, ctx: DurableContext) -> None:
    """Hard-delete only this tenant's explicit overrides; safe on replay."""
    await ctx.db.execute(
        delete(Setting).where(
            col(Setting.scope) == SCOPE_TENANT, col(Setting.scope_id) == event.tenant_id
        )
    )
