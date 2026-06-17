"""Inertia view endpoints for Branding."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from branding import constants

router = APIRouter()


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_VIEW))],
)
async def manage(inertia: InertiaDep) -> InertiaResponse:
    # Current branding is delivered through the shared ``branding`` prop
    # (the branding shared-props provider), so no page props are needed.
    return await inertia.render("Branding/Manage")
