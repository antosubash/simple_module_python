"""REST API endpoints for feature_flags management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_hosting.permissions import RequiresPermission

from feature_flags.constants import (
    PERM_FEATURE_FLAGS_MANAGE,
    PERM_FEATURE_FLAGS_VIEW,
    SCOPE_TENANT,
)
from feature_flags.contracts.schemas import FeatureFlagView, ToggleRequest
from feature_flags.deps import FeatureFlagRegistryDep, FeatureFlagServiceDep

router = APIRouter()


def _ensure_registered(name: str, registry: FeatureFlagRegistry) -> None:
    # A typo here would silently persist a dead row that ``list_flags`` filters out.
    if name not in {f.name for f in registry.all_flags}:
        raise HTTPException(status_code=404, detail="Feature flag not registered")


@router.get(
    "/",
    response_model=list[FeatureFlagView],
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_VIEW))],
)
async def list_flags(
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> list[FeatureFlagView]:
    return await service.list_flags(registry)


@router.get(
    "/{name}",
    response_model=FeatureFlagView,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_VIEW))],
)
async def get_flag(
    name: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> FeatureFlagView:
    view = service.build_view(registry, name)
    if view is None:
        raise HTTPException(status_code=404, detail="Feature flag not registered")
    return view


@router.put(
    "/{name}",
    response_model=FeatureFlagView,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def set_override(
    name: str,
    body: ToggleRequest,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> FeatureFlagView:
    _ensure_registered(name, registry)
    await service.set_override(name, body.enabled, registry=registry)
    view = service.build_view(registry, name)
    assert view is not None  # _ensure_registered already proved it exists
    return view


@router.delete(
    "/{name}",
    status_code=204,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def clear_override(
    name: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> None:
    cleared = await service.clear_override(name, registry=registry)
    if not cleared:
        raise HTTPException(status_code=404, detail="No override set for this flag")


@router.get(
    "/tenant/{tenant_id}",
    response_model=list[FeatureFlagView],
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_VIEW))],
)
async def list_flags_for_tenant(
    tenant_id: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> list[FeatureFlagView]:
    return await service.list_flags(registry, tenant_id=tenant_id)


@router.put(
    "/tenant/{tenant_id}/{name}",
    response_model=FeatureFlagView,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def set_tenant_override(
    tenant_id: str,
    name: str,
    body: ToggleRequest,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> FeatureFlagView:
    _ensure_registered(name, registry)
    await service.set_override(
        name, body.enabled, registry=registry, scope=SCOPE_TENANT, scope_id=tenant_id
    )
    view = service.build_view(registry, name, tenant_id=tenant_id)
    assert view is not None  # _ensure_registered already proved it exists
    return view


@router.delete(
    "/tenant/{tenant_id}/{name}",
    status_code=204,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def clear_tenant_override(
    tenant_id: str,
    name: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> None:
    cleared = await service.clear_override(
        name, registry=registry, scope=SCOPE_TENANT, scope_id=tenant_id
    )
    if not cleared:
        raise HTTPException(status_code=404, detail="No override set for this flag")
