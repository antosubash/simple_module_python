"""Platform administration of tenants: /admin/tenants (page) and /api/tenants/admin.

Spans tenants, so every route is gated by a ``tenants.platform.*`` permission,
which no tenant role grants.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse

from tenants.constants import PAGE_ADMIN, PERM_PLATFORM_MANAGE, PERM_PLATFORM_VIEW, TenantStatus
from tenants.contracts.schemas import TenantView
from tenants.deps import TenantServiceDep

views = APIRouter()
api = APIRouter(prefix="/admin")

_VIEW = [Depends(RequiresPermission(PERM_PLATFORM_VIEW))]
_MANAGE = [Depends(RequiresPermission(PERM_PLATFORM_MANAGE))]
_PAGE_SIZE = 50


@views.get("/", response_model=None, dependencies=_VIEW)
async def browse(
    inertia: InertiaDep, service: TenantServiceDep, q: str = "", page: int = 1
) -> InertiaResponse:
    page = max(page, 1)
    tenants = await service.list_all(search=q, limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE)
    counts = await service.member_counts([t.id for t in tenants])
    return await inertia.render(
        PAGE_ADMIN,
        {
            "tenants": [
                {
                    **TenantView(**t.model_dump()).model_dump(mode="json"),
                    "members": counts.get(t.id, 0),
                }
                for t in tenants
            ],
            "q": q,
            "page": page,
            "has_more": len(tenants) == _PAGE_SIZE,
        },
    )


@api.get("/", response_model=list[TenantView], dependencies=_VIEW)
async def list_tenants(service: TenantServiceDep, q: str = "") -> list[TenantView]:
    return [TenantView(**t.model_dump()) for t in await service.list_all(search=q)]


@api.post("/{tenant_id}/suspend", response_model=TenantView, dependencies=_MANAGE)
async def suspend(tenant_id: str, service: TenantServiceDep) -> TenantView:
    tenant = await service.set_status(tenant_id, TenantStatus.SUSPENDED)
    return TenantView(**tenant.model_dump())


@api.post("/{tenant_id}/reactivate", response_model=TenantView, dependencies=_MANAGE)
async def reactivate(tenant_id: str, service: TenantServiceDep) -> TenantView:
    tenant = await service.set_status(tenant_id, TenantStatus.ACTIVE)
    return TenantView(**tenant.model_dump())
