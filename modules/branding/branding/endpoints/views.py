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
    # The page name is inlined as a literal (rather than constants._PAGE_MANAGE)
    # so the SM003/SM004 diagnostics — which do static AST analysis and can't
    # resolve attribute access — pair this call with pages/Manage.tsx. A unit
    # test asserts the literal matches constants._PAGE_MANAGE.
    return await inertia.render(
        "Branding/Manage",
    )
