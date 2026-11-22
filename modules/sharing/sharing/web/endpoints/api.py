"""REST API for shares — mounted under ``/api/sharing``.

Gated on ``sharing.share`` (so an API token scoped to it may call these);
the resource's own policy then decides per row.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.user_directory import get_user_directory
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.rate_limit_deps import RateLimit
from simple_module_hosting.resource_deps import resource_principal

from sharing.contracts.schemas import ShareCandidate, ShareGrant, ShareOut, ShareSubjectType
from sharing.core.constants import CANDIDATES_DAILY_RATE, SUBJECT_USER, Permissions
from sharing.core.service import SharingError
from sharing.web.deps import SharingServiceDep, http_error
from sharing.web.present import present_shares

router = APIRouter(dependencies=[Depends(RequiresPermission(Permissions.SHARE))])


@router.get("/shares", response_model=list[ShareOut])
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
        get_user_directory(request.app),
        service.db,
        shares,
        service.audience,
        who,
        service.subject_registry(who),
    )


@router.post("/shares", response_model=ShareOut, status_code=201)
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
        get_user_directory(request.app),
        service.db,
        [share],
        service.audience,
        who,
        service.subject_registry(who),
    )
    return out


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(
    share_id: uuid.UUID,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> None:
    try:
        await service.revoke(who, share_id)
    except SharingError as exc:
        raise http_error(exc) from None


@router.get(
    "/candidates",
    response_model=list[ShareCandidate],
    dependencies=[Depends(RateLimit(CANDIDATES_DAILY_RATE, key="user"))],
)
async def share_candidates(
    resource_type: str,
    resource_id: str,
    service: SharingServiceDep,
    q: str = Query("", max_length=320),
    subject_type: str = Query(SUBJECT_USER, min_length=1, max_length=16),
    who: ResourcePrincipal = Depends(resource_principal),
) -> list[ShareCandidate]:
    try:
        return await service.candidates(who, resource_type, resource_id, q, subject_type)
    except SharingError as exc:
        raise http_error(exc) from None


@router.get("/subject-types", response_model=list[ShareSubjectType])
async def subject_types(
    resource_type: str,
    resource_id: str,
    service: SharingServiceDep,
    who: ResourcePrincipal = Depends(resource_principal),
) -> list[ShareSubjectType]:
    try:
        await service._authorize(who, service._type(resource_type), resource_id)
    except SharingError as exc:
        raise http_error(exc) from None
    return [
        ShareSubjectType(subject_type=p.name, label_key=p.label_key)
        for p in service.subject_registry(who).all()
    ]
