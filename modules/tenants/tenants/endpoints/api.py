"""JSON API for tenants, memberships and invitations (mounted at /api/tenants).

Tenant-level operations act on the request's *active* tenant (``/current``),
never on a tenant id from the URL: tenant roles grant permissions only inside
the active tenant, and taking the id from the path would let them reach any
other. Cross-tenant operations live in ``admin_api`` behind platform
permissions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from simple_module_core.permissions import grants
from simple_module_hosting.permissions import RequiresPermission, resolved_permissions_for

from tenants.constants import (
    PERM_MEMBERS_MANAGE,
    PERM_MEMBERS_VIEW,
    PERM_PLATFORM_MANAGE,
    MembershipRole,
    TenantStatus,
)
from tenants.contracts.schemas import (
    InvitationCreate,
    InvitationIssued,
    InvitationView,
    MemberView,
    MyTenantView,
    RoleChange,
    TenantCreate,
)
from tenants.deps import ActiveTenantDep, InvitationServiceDep, TenantServiceDep, UserIdDep
from tenants.errors import TenantError
from tenants.resolver import switch_active

router = APIRouter()

_VIEW = [Depends(RequiresPermission(PERM_MEMBERS_VIEW))]
_MANAGE = [Depends(RequiresPermission(PERM_MEMBERS_MANAGE))]


def _email_of(request: Request) -> str | None:
    return getattr(getattr(request.state, "user", None), "email", None)


@router.get("/", response_model=list[MyTenantView])
async def list_mine(user_id: UserIdDep, service: TenantServiceDep) -> list[MyTenantView]:
    rows = await service.list_for_user(user_id)
    return [MyTenantView(**t.model_dump(), role=role) for t, role in rows]


@router.post("/", response_model=MyTenantView, status_code=201)
async def create_tenant(
    data: TenantCreate, request: Request, user_id: UserIdDep, service: TenantServiceDep
) -> MyTenantView:
    settings = request.app.state.tenants.settings
    if not settings.allow_self_service and not grants(
        resolved_permissions_for(request), PERM_PLATFORM_MANAGE
    ):
        raise TenantError("self_service_disabled", status_code=403)
    tenant = await service.create_tenant(
        data, owner_user_id=user_id, owner_email=_email_of(request)
    )
    switch_active(request, tenant.id)
    return MyTenantView(**tenant.model_dump(), role=MembershipRole.OWNER)


@router.post("/{tenant_id}/switch", status_code=204)
async def switch_tenant(
    tenant_id: str, request: Request, user_id: UserIdDep, service: TenantServiceDep
) -> Response:
    membership = await service.get_membership(tenant_id, user_id)
    tenant = await service.get(tenant_id) if membership else None
    # Same answer for "no such tenant" and "not yours": ids are not enumerable.
    if membership is None or tenant is None:
        raise TenantError("not_found", status_code=404)
    if tenant.status != TenantStatus.ACTIVE:
        raise TenantError("tenant_suspended", status_code=409)
    switch_active(request, tenant_id)
    return Response(status_code=204)


# ── active tenant: members ─────────────────────────────────────


@router.get("/current/members", response_model=list[MemberView], dependencies=_VIEW)
async def list_members(ctx: ActiveTenantDep, service: TenantServiceDep) -> list[MemberView]:
    return [
        MemberView(user_id=m.user_id, email=m.email, role=m.role, joined_at=m.created_at)
        for m in await service.list_members(ctx.tenant_id)
    ]


@router.patch("/current/members/{user_id}", response_model=MemberView, dependencies=_MANAGE)
async def change_role(
    user_id: str, data: RoleChange, ctx: ActiveTenantDep, service: TenantServiceDep
) -> MemberView:
    m = await service.change_role(ctx.tenant_id, user_id, data.role, actor_role=ctx.role)
    return MemberView(user_id=m.user_id, email=m.email, role=m.role, joined_at=m.created_at)


@router.delete("/current/members/{user_id}", status_code=204, dependencies=_MANAGE)
async def remove_member(user_id: str, ctx: ActiveTenantDep, service: TenantServiceDep) -> Response:
    await service.remove_member(ctx.tenant_id, user_id, actor_role=ctx.role)
    return Response(status_code=204)


@router.delete("/current/membership", status_code=204)
async def leave(ctx: ActiveTenantDep, service: TenantServiceDep) -> Response:
    """Leave the active tenant. The last owner cannot leave."""
    await service.remove_member(ctx.tenant_id, ctx.user_id, actor_role=ctx.role)
    return Response(status_code=204)


# ── active tenant: invitations ─────────────────────────────────


@router.get("/current/invitations", response_model=list[InvitationView], dependencies=_MANAGE)
async def list_invitations(
    ctx: ActiveTenantDep, invitations: InvitationServiceDep
) -> list[InvitationView]:
    return [InvitationView(**i.model_dump()) for i in await invitations.list_pending(ctx.tenant_id)]


@router.post(
    "/current/invitations",
    response_model=InvitationIssued,
    status_code=201,
    dependencies=_MANAGE,
)
async def invite(
    data: InvitationCreate,
    request: Request,
    ctx: ActiveTenantDep,
    invitations: InvitationServiceDep,
) -> InvitationIssued:
    invitation, token, url = await invitations.create(
        ctx.tenant_id, data, base_url=str(request.base_url)
    )
    return InvitationIssued(**invitation.model_dump(), token=token, accept_url=url)


@router.delete("/current/invitations/{invitation_id}", status_code=204, dependencies=_MANAGE)
async def revoke_invitation(
    invitation_id: int, ctx: ActiveTenantDep, invitations: InvitationServiceDep
) -> Response:
    await invitations.revoke(ctx.tenant_id, invitation_id)
    return Response(status_code=204)


@router.post("/invitations/accept", response_model=MyTenantView)
async def accept_invitation(
    payload: dict[str, str],
    request: Request,
    user_id: UserIdDep,
    invitations: InvitationServiceDep,
) -> MyTenantView:
    email = _email_of(request)
    if not email:
        raise TenantError("invitation_email_mismatch", status_code=403)
    tenant = await invitations.accept(payload.get("token", ""), user_id=user_id, user_email=email)
    switch_active(request, tenant.id)
    membership = await invitations.tenants.get_membership(tenant.id, user_id)
    role = membership.role if membership else MembershipRole.MEMBER
    return MyTenantView(**tenant.model_dump(), role=role)
