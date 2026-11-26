"""Admin REST API for shares — mounted under ``/api/sharing/admin``.

Mirrors the admin page (``sharing.view`` to list, ``sharing.manage`` to revoke)
and deliberately sits outside the ``sharing.share`` router in ``api.py``, so a
token scoped to the admin permissions does not also need ``sharing.share``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.user_directory import get_user_directory
from simple_module_db import paginate
from simple_module_db.queries.pagination import Page
from simple_module_hosting.auth.csrf import RequiresCsrf
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.auth.resource_deps import resource_principal
from simple_module_hosting.frontend.pagination import PageParamsDep
from sqlmodel import col, select

from sharing.contracts.schemas import ShareOut
from sharing.core.constants import ADMIN_API_PATH, Permissions
from sharing.core.service import SharingError
from sharing.models import ResourceShare
from sharing.web.deps import SharingServiceDep, http_error
from sharing.web.present import present_shares

router = APIRouter(prefix=ADMIN_API_PATH)


@router.get(
    "/shares",
    response_model=Page[ShareOut],
    dependencies=[Depends(RequiresPermission(Permissions.VIEW))],
)
async def admin_list_shares(
    request: Request,
    service: SharingServiceDep,
    params: PageParamsDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> Page[ShareOut]:
    stmt = select(ResourceShare).order_by(
        col(ResourceShare.created_at).desc(), col(ResourceShare.id)
    )
    page = await paginate(service.db, stmt, params)
    items = await present_shares(
        get_user_directory(request.app),
        service.db,
        page.items,
        service.audience,
        who,
        service.subject_registry(who),
    )
    return Page(
        items=items, total=page.total, page=page.page, per_page=page.per_page, pages=page.pages
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
