"""FastAPI dependencies for the Tenants module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.errors import TenantError
from tenants.invitations import InvitationService
from tenants.resolver import make_invalidator
from tenants.service import TenantService


def get_tenant_service(request: Request, db: AsyncSession = Depends(get_db)) -> TenantService:
    app = request.app
    return TenantService(
        db,
        bus=app.state.sm.event_bus,
        invalidate=make_invalidator(app),
        entitlements=app.state.tenants.entitlements,
    )


TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]


def get_invitation_service(request: Request, tenants: TenantServiceDep) -> InvitationService:
    ttl = request.app.state.tenants.settings.invitation_ttl_hours
    return InvitationService(tenants, ttl_hours=ttl)


InvitationServiceDep = Annotated[InvitationService, Depends(get_invitation_service)]


@dataclass(frozen=True)
class ActiveTenantContext:
    tenant_id: str
    role: str
    user_id: str


def require_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        raise TenantError("not_authenticated", status_code=401)
    return str(user.id)


def require_active_tenant(request: Request) -> ActiveTenantContext:
    """The tenant resolved for this request. Operations act on it — never on an
    id from the URL — so a tenant-level permission cannot reach another tenant."""
    user_id = require_user_id(request)
    tenant_id = getattr(request.state, "tenant_id", None)
    role = getattr(request.state, "tenant_role", None)
    if tenant_id is None or role is None:
        raise TenantError("tenant_required", status_code=403)
    return ActiveTenantContext(tenant_id=tenant_id, role=role, user_id=user_id)


UserIdDep = Annotated[str, Depends(require_user_id)]
ActiveTenantDep = Annotated[ActiveTenantContext, Depends(require_active_tenant)]
