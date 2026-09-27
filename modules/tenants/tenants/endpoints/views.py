"""Inertia pages for organisations (mounted at /tenants).

Pages read; mutations go through the JSON API with ``fetch`` followed by an
Inertia reload (``SM018``: Inertia's router rejects JSON responses).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from simple_module_core.permissions import grants
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission, resolved_permissions_for
from simple_module_inertia import InertiaResponse

from tenants.constants import (
    ENTITLEMENT_SEATS,
    PAGE_ACCEPT,
    PAGE_INDEX,
    PAGE_MEMBERS,
    PERM_MEMBERS_MANAGE,
    PERM_MEMBERS_VIEW,
    PERM_PLATFORM_MANAGE,
)
from tenants.deps import InvitationServiceDep, TenantServiceDep, UserIdDep
from tenants.resolver import memberships_for

router = APIRouter()


def _perm(request: Request, permission: str) -> bool:
    return grants(resolved_permissions_for(request), permission)


@router.get("/", response_model=None)
async def index(
    request: Request, inertia: InertiaDep, user_id: UserIdDep, reason: str | None = None
) -> InertiaResponse:
    memberships = await memberships_for(request.app, user_id)
    settings = request.app.state.tenants.settings
    return await inertia.render(
        PAGE_INDEX,
        {
            "memberships": [m.model_dump(mode="json") for m in memberships],
            "active_id": getattr(request.state, "tenant_id", None),
            "suspended": bool(getattr(request.state, "tenant_suspended", False)),
            "can_create": settings.allow_self_service or _perm(request, PERM_PLATFORM_MANAGE),
            "reason": reason,
        },
    )


@router.get(
    "/members",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_MEMBERS_VIEW))],
)
async def members(
    request: Request,
    inertia: InertiaDep,
    service: TenantServiceDep,
    invitations: InvitationServiceDep,
) -> InertiaResponse | RedirectResponse:
    tenant_id = getattr(request.state, "tenant_id", None)
    tenant = await service.get(tenant_id) if tenant_id else None
    if tenant is None:
        return RedirectResponse("/tenants?reason=tenant_required", status_code=303)
    can_manage = _perm(request, PERM_MEMBERS_MANAGE)
    pending = await invitations.list_pending(tenant.id) if can_manage else []
    limit = await service.entitlements.limit(tenant.id, ENTITLEMENT_SEATS)
    return await inertia.render(
        PAGE_MEMBERS,
        {
            "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
            "my_role": request.state.tenant_role,
            "my_user_id": str(request.state.user.id),
            "can_manage": can_manage,
            "members": [
                {
                    "user_id": m.user_id,
                    "email": m.email,
                    "role": m.role,
                    "joined_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in await service.list_members(tenant.id)
            ],
            "invitations": [i.model_dump(mode="json", exclude={"token_hash"}) for i in pending],
            "seats": {"used": await service.seats_used(tenant.id), "limit": limit},
        },
    )


@router.get("/invitations/accept", response_model=None)
async def accept_invitation(
    request: Request, inertia: InertiaDep, invitations: InvitationServiceDep, token: str = ""
) -> InertiaResponse:
    found = await invitations.lookup(token)
    preview = None
    if found is not None:
        invitation, tenant = found
        preview = {
            "tenant_name": tenant.name,
            "email": invitation.email,
            "role": invitation.role,
            "expired": invitations.is_expired(invitation),
            "accepted": invitation.accepted_at is not None,
        }
    user = getattr(request.state, "user", None)
    return await inertia.render(
        PAGE_ACCEPT,
        {"token": token, "invitation": preview, "signed_in_as": getattr(user, "email", None)},
    )
