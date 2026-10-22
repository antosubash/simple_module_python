"""The admin page — mounted under ``/admin/sharing``."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from simple_module_core.resources import ResourcePrincipal
from simple_module_core.user_directory import get_user_directory
from simple_module_db import TenantIsolationError, paginate
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.pagination import LenientPageParamsDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.resource_deps import resource_principal
from simple_module_inertia import InertiaResponse
from sqlmodel import col, select
from starlette.responses import RedirectResponse

from sharing.constants import ADMIN_URL, PAGE_ADMIN, PERM_MANAGE, PERM_VIEW
from sharing.deps import SharingServiceDep, http_error
from sharing.models import ResourceShare
from sharing.present import present_shares
from sharing.service import SharingError

router = APIRouter()


@router.get("/", response_model=None, dependencies=[Depends(RequiresPermission(PERM_VIEW))])
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: SharingServiceDep,
    params: LenientPageParamsDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> InertiaResponse:
    stmt = select(ResourceShare).order_by(
        col(ResourceShare.created_at).desc(), col(ResourceShare.id)
    )
    try:
        page = await paginate(service.db, stmt, params)
        shares = await present_shares(get_user_directory(request.app), service.db, page.items)
        total, served, tenant_required = page.total, page.page, False
    except TenantIsolationError:
        # Strict tenancy with no active tenant: nothing to list.
        shares, total, served, tenant_required = [], 0, 1, True
    return await inertia.render(
        PAGE_ADMIN,
        {
            "shares": [s.model_dump(mode="json") for s in shares],
            "total": total,
            "page": served,
            "per_page": params.per_page,
            "can_revoke": who.has(PERM_MANAGE),
            "tenant_required": tenant_required,
        },
    )


@router.post(
    "/{share_id}/revoke",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
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
