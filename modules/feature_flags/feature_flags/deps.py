"""FastAPI dependencies for the feature_flags module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.tenancy import tenant_exists
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from feature_flags.service import FeatureFlagService


async def get_feature_flag_service(
    db: AsyncSession = Depends(get_db),
) -> FeatureFlagService:
    return FeatureFlagService(db)


def get_feature_flag_registry(request: Request) -> FeatureFlagRegistry:
    """Return the process-wide FeatureFlagRegistry owned by the framework."""
    return request.app.state.sm.feature_flags


async def require_known_tenant(request: Request, tenant_id: str | None = None) -> None:
    """404 when a tenant-scope screen names a tenant that does not exist.

    Without it a typo in the URL persists an override for a tenant nobody has,
    which nothing ever reads. The lookup goes through core's ``tenant_exists``
    (``app.state.tenant_exists``, published by the ``tenants`` module), so this
    module does not depend on ``tenants``; with none installed any id is
    accepted, as before. No id (system scope) is always fine.
    """
    if tenant_id and await tenant_exists(request.app, tenant_id) is False:
        raise HTTPException(status_code=404, detail="Tenant not found")


FeatureFlagServiceDep = Annotated[FeatureFlagService, Depends(get_feature_flag_service)]
FeatureFlagRegistryDep = Annotated[FeatureFlagRegistry, Depends(get_feature_flag_registry)]
