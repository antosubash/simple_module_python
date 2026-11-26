"""Admin REST API for shares — mounted under ``/api/sharing/admin``.

Mirrors the admin page (``sharing.view`` to list, ``sharing.manage`` to revoke)
and deliberately sits outside the ``sharing.share`` router in ``api.py``, so a
token scoped to the admin permissions does not also need ``sharing.share``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_db import TenantIsolationError
from simple_module_hosting.auth.csrf import RequiresCsrf
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.auth.resource_deps import resource_principal
from simple_module_hosting.frontend.pagination import PageParamsDep

from sharing.contracts.schemas import SharePage
from sharing.core.constants import ADMIN_API_PATH, Permissions
from sharing.core.service import SharingError
from sharing.web.deps import SharingServiceDep, http_error
from sharing.web.listing import list_admin_shares

TENANT_REQUIRED = "tenant_required"

router = APIRouter(prefix=ADMIN_API_PATH)


@router.get(
    "/shares",
    response_model=SharePage,
    dependencies=[Depends(RequiresPermission(Permissions.VIEW))],
)
async def admin_list_shares(
    request: Request,
    service: SharingServiceDep,
    params: PageParamsDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> SharePage:
    listing = await list_admin_shares(request, service, params, who)
    return SharePage(
        items=listing.shares,
        total=listing.total,
        page=listing.page,
        per_page=params.per_page,
        pages=listing.pages,
    )


@router.post(
    "/shares/{share_id}/revoke",
    status_code=204,
    dependencies=[Depends(RequiresPermission(Permissions.MANAGE)), Depends(RequiresCsrf())],
)
async def admin_revoke_share(
    share_id: uuid.UUID,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> None:
    try:
        await service.revoke(who, share_id)
    except SharingError as exc:
        raise http_error(exc) from None
    except TenantIsolationError:
        # Strict tenancy and no active tenant (a platform admin before picking one):
        # same fail-closed answer the tenant-level APIs give.
        raise HTTPException(status_code=403, detail=TENANT_REQUIRED) from None
