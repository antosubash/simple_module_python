"""REST API for shares — mounted under ``/api/sharing``.

Gated on ``sharing.share`` (so an API token scoped to it may call these);
the resource's own policy then decides per row.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from simple_module_core.resources import ResourcePrincipal
from simple_module_core.user_directory import get_user_directory
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.resource_deps import resource_principal

from sharing.constants import PERM_SHARE
from sharing.contracts.schemas import ShareGrant, ShareOut
from sharing.deps import SharingServiceDep, http_error
from sharing.present import present_shares
from sharing.service import SharingError

router = APIRouter(prefix="/shares", dependencies=[Depends(RequiresPermission(PERM_SHARE))])


@router.get("", response_model=list[ShareOut])
async def list_shares(
    request: Request,
    resource_type: str,
    resource_id: str,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> list[ShareOut]:
    try:
        shares = await service.for_resource(who, resource_type, resource_id)
    except SharingError as exc:
        raise http_error(exc) from None
    return await present_shares(
        get_user_directory(request.app), service.db, shares, service.audience
    )


@router.post("", response_model=ShareOut, status_code=201)
async def grant_share(
    request: Request,
    data: ShareGrant,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> ShareOut:
    try:
        share = await service.grant(who, data)
    except SharingError as exc:
        raise http_error(exc) from None
    (out,) = await present_shares(
        get_user_directory(request.app), service.db, [share], service.audience
    )
    return out


@router.delete("/{share_id}", status_code=204)
async def revoke_share(
    share_id: uuid.UUID,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> None:
    try:
        await service.revoke(who, share_id)
    except SharingError as exc:
        raise http_error(exc) from None
