"""JSON API for administrators: every token in the tenant, and service keys.

Session-only and CSRF-checked like the personal API, and gated on
``api_tokens.manage``. Reads and revokes are tenant-scoped (fail-closed): an
administrator acts on the active tenant, never one named in the URL.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from simple_module_db import TenantIsolationError
from simple_module_hosting.csrf import RequiresCsrf
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from api_tokens.constants import FORBIDDEN_SERVICE_ROLES, PERM_MANAGE, TokenKind
from api_tokens.contracts.schemas import CreatedToken, ServiceKeyCreate, TokenView
from api_tokens.deps import ApiTokenServiceDep, SettingsDep, http_error, require_session_principal
from api_tokens.scopes import assignable_roles, assignable_scopes, check_subset
from api_tokens.service import ApiTokenService, TokenError

router = APIRouter(
    prefix="/admin",
    dependencies=[
        Depends(require_session_principal),
        Depends(RequiresCsrf()),
        Depends(RequiresPermission(PERM_MANAGE)),
    ],
)


async def tenant_token_views(
    service: ApiTokenService, *, limit: int = 100, offset: int = 0
) -> list[TokenView]:
    tokens = await service.list_tenant(limit=limit, offset=offset)
    emails = await service.owner_emails(tokens)
    return [
        service.to_view(t, emails.get(t.owner_user_id) if t.owner_user_id else None) for t in tokens
    ]


@router.get("/tokens", response_model=list[TokenView])
async def list_all(
    service: ApiTokenServiceDep,
    t: TranslatorDep,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[TokenView]:
    try:
        return await tenant_token_views(service, limit=limit, offset=offset)
    except TenantIsolationError:
        raise HTTPException(
            status_code=409, detail=t.t("api_tokens.errors.tenant_required")
        ) from None


@router.post("/service-keys", response_model=CreatedToken, status_code=201)
async def create_service_key(
    body: ServiceKeyCreate,
    request: Request,
    service: ApiTokenServiceDep,
    settings: SettingsDep,
    t: TranslatorDep,
) -> CreatedToken:
    try:
        forbidden = sorted(set(body.roles) & FORBIDDEN_SERVICE_ROLES)
        if forbidden:
            raise TokenError("api_tokens.errors.role_forbidden", role=forbidden[0])
        roles = check_subset(
            body.roles, assignable_roles(request), "api_tokens.errors.role_not_assignable"
        )
        scopes = check_subset(
            body.scopes, await assignable_scopes(request), "api_tokens.errors.scope_not_held"
        )
        token, plaintext = await service.create(
            kind=TokenKind.SERVICE,
            name=body.name,
            scopes=scopes,
            roles=roles,
            expires_in_days=body.expires_in_days,
            max_lifetime_days=settings.max_lifetime_days,
        )
    except TokenError as exc:
        raise http_error(t, exc) from None
    except TenantIsolationError:
        raise HTTPException(
            status_code=409, detail=t.t("api_tokens.errors.tenant_required")
        ) from None
    return CreatedToken(token=plaintext, item=service.to_view(token))


@router.post("/tokens/{token_id}/revoke", response_model=TokenView)
async def revoke_any(
    token_id: uuid.UUID, service: ApiTokenServiceDep, t: TranslatorDep
) -> TokenView:
    try:
        token = await service.get_in_tenant(token_id)
    except TenantIsolationError:
        token = None
    if token is None:
        raise HTTPException(status_code=404, detail=t.t("api_tokens.errors.not_found"))
    await service.revoke(token)
    return service.to_view(token)
