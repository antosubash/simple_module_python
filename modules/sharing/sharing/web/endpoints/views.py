"""The admin page — mounted under ``/admin/sharing``."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.auth.resource_deps import resource_principal
from simple_module_hosting.frontend.inertia_deps import InertiaDep
from simple_module_hosting.frontend.pagination import LenientPageParamsDep
from simple_module_inertia import InertiaResponse
from starlette.responses import RedirectResponse

from sharing.core.constants import ADMIN_URL, PAGE_ADMIN, Permissions
from sharing.core.service import SharingError
from sharing.web.deps import SharingServiceDep, http_error
from sharing.web.listing import list_admin_shares

router = APIRouter()


@router.get("/", response_model=None, dependencies=[Depends(RequiresPermission(Permissions.VIEW))])
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: SharingServiceDep,
    params: LenientPageParamsDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> InertiaResponse:
    listing = await list_admin_shares(request, service, params, who)
    shares, total, served = listing.shares, listing.total, listing.page
    tenant_required = listing.tenant_required
    return await inertia.render(
        PAGE_ADMIN,
        {
            "shares": [s.model_dump(mode="json") for s in shares],
            "total": total,
            "page": served,
            "per_page": params.per_page,
            "can_revoke": who.has(Permissions.MANAGE),
            "tenant_required": tenant_required,
        },
    )


@router.post(
    "/{share_id}/revoke",
    response_model=None,
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE))],
)
async def admin_revoke(
    share_id: uuid.UUID,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> RedirectResponse:
    try:
        await service.revoke(who, share_id)
    except SharingError as exc:
        raise http_error(exc) from None
    return RedirectResponse(ADMIN_URL, status_code=303)
