"""FastAPI dependencies for the feature_flags module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_core.feature_flags import FeatureFlagRegistry
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


FeatureFlagServiceDep = Annotated[FeatureFlagService, Depends(get_feature_flag_service)]
FeatureFlagRegistryDep = Annotated[FeatureFlagRegistry, Depends(get_feature_flag_registry)]
