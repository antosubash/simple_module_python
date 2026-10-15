"""FastAPI dependencies for the api_tokens module."""

from __future__ import annotations

import uuid
from typing import Annotated

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION
from fastapi import Depends, HTTPException, Request
from simple_module_db.deps import get_db
from simple_module_hosting.i18n_deps import TranslatorDep
from sqlalchemy.ext.asyncio import AsyncSession

from api_tokens.service import ApiTokenService, TokenError
from api_tokens.settings import ApiTokensSettings


async def get_api_token_service(db: AsyncSession = Depends(get_db)) -> ApiTokenService:
    return ApiTokenService(db)


def get_settings(request: Request) -> ApiTokensSettings:
    return request.app.state.api_tokens.settings


async def require_session_principal(request: Request, t: TranslatorDep) -> UserContext:
    """The signed-in person — refusing any token-authenticated request.

    Tokens may not mint, list or revoke tokens: a leaked token must not be
    able to make itself permanent by creating a sibling, or hide by revoking
    the one an administrator would look for. That covers a provider's own
    bearer credential too (``auth_kind == "bearer"``): a fifteen-minute access
    token must not become a year-long PAT. Only a cookie session qualifies, so
    any request carrying an ``Authorization`` header is refused outright.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail=t.t("auth.errors.not_authenticated"))
    if (
        getattr(user, "auth_kind", None) != AUTH_KIND_SESSION
        or getattr(user, "scopes", None) is not None
        or "authorization" in request.headers
    ):
        raise HTTPException(status_code=403, detail=t.t("api_tokens.errors.session_required"))
    return user


def user_uuid(user: UserContext, t) -> uuid.UUID:
    """The signed-in user's id as a UUID; 403 for a principal that is not an account."""
    try:
        return uuid.UUID(str(user.id))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=403, detail=t.t("api_tokens.errors.session_required")
        ) from None


def http_error(t, exc: TokenError) -> HTTPException:
    """Translate a service refusal into a 422 the pages can show as-is."""
    return HTTPException(status_code=422, detail=t.t(exc.key, **exc.params))


ApiTokenServiceDep = Annotated[ApiTokenService, Depends(get_api_token_service)]
SettingsDep = Annotated[ApiTokensSettings, Depends(get_settings)]
SessionPrincipal = Annotated[UserContext, Depends(require_session_principal)]
