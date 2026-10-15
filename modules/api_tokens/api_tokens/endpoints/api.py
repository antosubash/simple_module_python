"""JSON API for a user's own personal access tokens.

Session-only (``require_session_principal``) and CSRF-checked on every
mutation: the pages call these with the session cookie, and a token may never
manage tokens.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_db import TenantIsolationError
from simple_module_hosting.csrf import RequiresCsrf
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import RequiresPermission

from api_tokens.constants import PERM_USE, TokenKind
from api_tokens.contracts.schemas import CreatedToken, PersonalTokenCreate, TokenView
from api_tokens.deps import (
    ApiTokenServiceDep,
    SessionPrincipal,
    SettingsDep,
    http_error,
    require_session_principal,
    user_uuid,
)
from api_tokens.scopes import assignable_scopes, check_subset
from api_tokens.service import TokenError

router = APIRouter(
    prefix="/tokens",
    dependencies=[
        Depends(require_session_principal),
        Depends(RequiresCsrf()),
        Depends(RequiresPermission(PERM_USE)),
    ],
)


@router.get("/", response_model=list[TokenView])
async def list_tokens(
    user: SessionPrincipal, service: ApiTokenServiceDep, t: TranslatorDep
) -> list[TokenView]:
    tokens = await service.list_for_owner(user_uuid(user, t))
    return [service.to_view(token) for token in tokens]


@router.post("/", response_model=CreatedToken, status_code=201)
async def create_token(
    body: PersonalTokenCreate,
    request: Request,
    user: SessionPrincipal,
    service: ApiTokenServiceDep,
    settings: SettingsDep,
    t: TranslatorDep,
) -> CreatedToken:
    owner = user_uuid(user, t)
    try:
        scopes = check_subset(
            body.scopes, await assignable_scopes(request), "api_tokens.errors.scope_not_held"
        )
        token, plaintext = await service.create(
            kind=TokenKind.PERSONAL,
            name=body.name,
            scopes=scopes,
            expires_in_days=body.expires_in_days,
            max_lifetime_days=settings.max_lifetime_days,
            owner_user_id=owner,
        )
    except TokenError as exc:
        raise http_error(t, exc) from None
    except TenantIsolationError:
        raise HTTPException(
            status_code=409, detail=t.t("api_tokens.errors.tenant_required")
        ) from None
    return CreatedToken(token=plaintext, item=service.to_view(token))


@router.post("/{token_id}/revoke", response_model=TokenView)
async def revoke_token(
    token_id: uuid.UUID, user: SessionPrincipal, service: ApiTokenServiceDep, t: TranslatorDep
) -> TokenView:
    token = await service.get_owned(token_id, user_uuid(user, t))
    if token is None:
        raise HTTPException(status_code=404, detail=t.t("api_tokens.errors.not_found"))
    await service.revoke(token, cross_tenant=True)
    return service.to_view(token)
