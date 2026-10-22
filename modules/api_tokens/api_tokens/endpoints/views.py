"""Inertia pages: ``/api-tokens/`` (your own tokens), ``/admin/api-tokens/`` (all).

Both pages only render; every change goes through the JSON API with the CSRF
token handed out here, because the one response carrying a new token's
secret has to reach the page as data, not as a redirect.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from simple_module_db import TenantIsolationError
from simple_module_hosting.csrf import get_csrf_token
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse

from api_tokens.constants import (
    EXPIRY_PRESETS_DAYS,
    PAGE_ADMIN,
    PAGE_INDEX,
    PERM_MANAGE,
    PERM_USE,
)
from api_tokens.deps import (
    ApiTokenServiceDep,
    SessionPrincipal,
    SettingsDep,
    require_session_principal,
    user_uuid,
)
from api_tokens.endpoints.admin_api import tenant_token_views
from api_tokens.scopes import assignable_roles, assignable_scopes

router = APIRouter(
    dependencies=[Depends(require_session_principal), Depends(RequiresPermission(PERM_USE))]
)
admin_router = APIRouter(
    dependencies=[Depends(require_session_principal), Depends(RequiresPermission(PERM_MANAGE))]
)


def _form_props(request: Request, max_days: int) -> dict:
    return {
        "max_lifetime_days": max_days,
        "expiry_presets": [d for d in EXPIRY_PRESETS_DAYS if d <= max_days] or [max_days],
        "csrf_token": get_csrf_token(request),
    }


@router.get("/", response_model=None)
async def index(
    request: Request,
    inertia: InertiaDep,
    user: SessionPrincipal,
    service: ApiTokenServiceDep,
    settings: SettingsDep,
    t: TranslatorDep,
) -> InertiaResponse:
    tokens = await service.list_for_owner(user_uuid(user, t))
    return await inertia.render(
        PAGE_INDEX,
        {
            "tokens": [service.to_view(tok).model_dump(mode="json") for tok in tokens],
            "scopes": await assignable_scopes(request),
            **_form_props(request, settings.max_lifetime_days),
        },
    )


@admin_router.get("/", response_model=None)
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: ApiTokenServiceDep,
    settings: SettingsDep,
) -> InertiaResponse:
    try:
        views = await tenant_token_views(service)
        tenant_required = False
    except TenantIsolationError:
        # Strict tenancy with no active tenant: nothing to list, and nowhere
        # to create a service key. The page says so instead of a 500.
        views, tenant_required = [], True
    return await inertia.render(
        PAGE_ADMIN,
        {
            "tokens": [v.model_dump(mode="json") for v in views],
            "scopes": await assignable_scopes(request),
            "roles": assignable_roles(request),
            "tenant_required": tenant_required,
            **_form_props(request, settings.max_lifetime_days),
        },
    )
