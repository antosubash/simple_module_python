"""Inertia view endpoints for feature_flags admin UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from feature_flags.constants import (
    MENU_URL,
    PAGE_BROWSE,
    PERM_FEATURE_FLAGS_MANAGE,
    PERM_FEATURE_FLAGS_VIEW,
)
from feature_flags.deps import FeatureFlagRegistryDep, FeatureFlagServiceDep

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_VIEW))],
)
async def browse(
    inertia: InertiaDep,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> InertiaResponse:
    flags = await service.list_flags(registry)
    return await inertia.render(
        PAGE_BROWSE,
        {"flags": [f.model_dump(mode="json") for f in flags]},
    )


@router.post(
    "/{name}/toggle",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def toggle_action(
    name: str,
    request: Request,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> RedirectResponse:
    if name not in {f.name for f in registry.all_flags}:
        return RedirectResponse(MENU_URL, status_code=303)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    await service.set_override(name, enabled, registry=registry)
    return RedirectResponse(MENU_URL, status_code=303)


@router.post(
    "/{name}/clear",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def clear_action(
    name: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
) -> RedirectResponse:
    await service.clear_override(name, registry=registry)
    return RedirectResponse(MENU_URL, status_code=303)
