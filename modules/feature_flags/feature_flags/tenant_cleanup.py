"""Durable cleanup of tenant-scoped feature flag overrides."""

from simple_module_core.durable_events import DurableContext
from simple_module_core.tenant_events import TenantDeleted
from sqlmodel import col, delete

from feature_flags.constants import SCOPE_TENANT
from feature_flags.models import FeatureFlagOverride


async def purge_tenant_data(event: TenantDeleted, ctx: DurableContext) -> None:
    """Keep system/other tenants' overrides; acknowledge with the worker transaction."""
    await ctx.db.execute(
        delete(FeatureFlagOverride).where(
            col(FeatureFlagOverride.scope) == SCOPE_TENANT,
            col(FeatureFlagOverride.scope_id) == event.tenant_id,
        )
    )
