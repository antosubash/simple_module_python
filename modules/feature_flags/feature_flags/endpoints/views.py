"""Inertia view endpoints for feature_flags admin UI.

The browse page renders either system-scope or a tenant-scope view of the
flags. Tenant scope is selected via a ``tenant_id`` query string. The form
actions for toggling/clearing accept the same ``tenant_id`` query so the
frontend doesn't need separate routes per scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from feature_flags.constants import (
    AUDIT_LOG_MODULE,
    AUDIT_LOG_VIEW_URL,
    MENU_URL,
    PAGE_BROWSE,
    PERM_FEATURE_FLAGS_MANAGE,
    PERM_FEATURE_FLAGS_VIEW,
    QP_TENANT_ID,
    SCOPE_SYSTEM,
    SCOPE_TENANT,
    SYSTEM_SCOPE_ID,
)
from feature_flags.deps import FeatureFlagRegistryDep, FeatureFlagServiceDep

router = APIRouter()


def _redirect_for_tenant(tenant_id: str | None) -> RedirectResponse:
    target = MENU_URL if not tenant_id else f"{MENU_URL}?{QP_TENANT_ID}={tenant_id}"
    return RedirectResponse(target, status_code=303)


def _audit_log_url(request: Request) -> str | None:
    """Where "View change history" points, or ``None`` when nothing is there.

    The audit log is an ordinary installable module, not a dependency of this
    one — offering a link to a screen the install does not have is a 404 with
    extra steps. Built from the model class name because that is the key the
    trail is written under.
    """
    from feature_flags.models import FeatureFlagOverride

    installed = any(m.meta.name == AUDIT_LOG_MODULE for m in request.app.state.sm.modules)
    if not installed:
        return None
    return f"{AUDIT_LOG_VIEW_URL}?entity_type={FeatureFlagOverride.__name__}"


def _scope_args(tenant_id: str | None) -> dict[str, str]:
    if tenant_id:
        return {"scope": SCOPE_TENANT, "scope_id": tenant_id}
    return {"scope": SCOPE_SYSTEM, "scope_id": SYSTEM_SCOPE_ID}


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_VIEW))],
)
async def browse(
    request: Request,
    inertia: InertiaDep,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
    tenant_id: str | None = None,
) -> InertiaResponse:
    flags = await service.list_flags(registry, tenant_id=tenant_id)
    tenants = await service.list_tenants_with_overrides()
    return await inertia.render(
        PAGE_BROWSE,
        {
            "flags": [f.model_dump(mode="json") for f in flags],
            "tenant_id": tenant_id,
            "tenants": tenants,
            "audit_log_url": _audit_log_url(request),
        },
    )


@router.post(
    "/{name}/toggle",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def toggle_action(
    name: str,
    request: Request,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
    tenant_id: str | None = None,
) -> RedirectResponse:
    if name not in {f.name for f in registry.all_flags}:
        return _redirect_for_tenant(tenant_id)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    await service.set_override(name, enabled, registry=registry, **_scope_args(tenant_id))
    return _redirect_for_tenant(tenant_id)


@router.post(
    "/{name}/clear",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_FEATURE_FLAGS_MANAGE))],
)
async def clear_action(
    name: str,
    service: FeatureFlagServiceDep,
    registry: FeatureFlagRegistryDep,
    tenant_id: str | None = None,
) -> RedirectResponse:
    await service.clear_override(name, registry=registry, **_scope_args(tenant_id))
    return _redirect_for_tenant(tenant_id)
