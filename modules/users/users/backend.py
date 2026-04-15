"""Auth backend — cookie transport + DB access-token strategy."""

from __future__ import annotations

from fastapi import Depends
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import (
    AccessTokenDatabase,
    DatabaseStrategy,
)

from users.db_adapter import get_access_token_db
from users.models import UserAccessToken


def build_cookie_transport(
    cookie_name: str,
    cookie_max_age_seconds: int,
    cookie_secure: bool,
    cookie_samesite: str,
) -> CookieTransport:
    return CookieTransport(
        cookie_name=cookie_name,
        cookie_max_age=cookie_max_age_seconds,
        cookie_secure=cookie_secure,
        cookie_httponly=True,
        cookie_samesite=cookie_samesite,  # type: ignore[arg-type]
    )


def get_database_strategy(
    access_token_db: AccessTokenDatabase[UserAccessToken] = Depends(get_access_token_db),
    lifetime_seconds: int = 60 * 60 * 24 * 14,
) -> DatabaseStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=lifetime_seconds)


def build_auth_backend(
    cookie_transport: CookieTransport,
) -> AuthenticationBackend:
    return AuthenticationBackend(
        name="cookie",
        transport=cookie_transport,
        get_strategy=get_database_strategy,
    )
