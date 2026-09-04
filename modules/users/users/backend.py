"""Auth backend — cookie transport + DB access-token strategy.

The AuthenticationBackend is constructed once at import time in ``deps.py``
with dev-safe defaults so ``fastapi_users.current_user(...)`` — which is
captured by route-handler ``Depends(...)`` signatures at import time — has
a stable instance to bind against.

Real settings are applied at startup via :func:`reconfigure_cookie_transport`,
which updates the singleton's ``CookieTransport`` fields in place. Because
this reaches into fastapi-users' instance state, the package's major version
is pinned narrowly in pyproject.toml.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import (
    AccessTokenDatabase,
    DatabaseStrategy,
)

from users.db_adapter import get_access_token_db
from users.models import UserAccessToken

if TYPE_CHECKING:
    from users.settings import UsersSettings

_TOKEN_LIFETIME_SECONDS = 60 * 60 * 24 * 30  # 30 days
"""Oldest access-token row still accepted — the ceiling, not the norm.

This is the *read* window, and there is only one of it: ``current_user``
resolves its strategy from the shared backend, so it cannot vary per request.
A remembered sign-in writes a row it needs for thirty days, and reading it back
against a fourteen-day window would have signed those people out halfway
through the window the checkbox promised.

What actually bounds an ordinary session is the cookie's own ``Max-Age``
(``UsersSettings.cookie_max_age_seconds``, fourteen days), which the browser
enforces by dropping it. Same shape as the session cookie's signature window in
``simple_module_hosting.session``: one long acceptance window, a short cookie
window unless the person asked for more. Revocation does not depend on either —
"sign out everywhere" bumps ``User.session_version``, which is checked on every
request.
"""

_AUTH_BACKEND_NAME = "cookie"


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
    lifetime_seconds: int = _TOKEN_LIFETIME_SECONDS,
) -> DatabaseStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=lifetime_seconds)


def build_auth_backend(
    cookie_transport: CookieTransport,
) -> AuthenticationBackend:
    return AuthenticationBackend(
        name=_AUTH_BACKEND_NAME,
        transport=cookie_transport,
        get_strategy=get_database_strategy,
    )


def reconfigure_cookie_transport(
    backend: AuthenticationBackend,
    settings: UsersSettings,
) -> None:
    """Apply production cookie config to an already-constructed backend.

    Called from ``UsersModule.on_startup`` once the real ``UsersSettings``
    is available on ``app.state``. This is the one place that depends on
    fastapi-users' ``CookieTransport`` field names; any upstream rename
    surfaces here rather than scattered across the codebase.
    """
    transport = backend.transport
    assert isinstance(transport, CookieTransport), (
        f"users auth_backend.transport must be a CookieTransport, got {type(transport)!r}"
    )
    transport.cookie_name = settings.cookie_name
    transport.cookie_max_age = settings.cookie_max_age_seconds
    transport.cookie_secure = settings.cookie_secure
    transport.cookie_samesite = settings.cookie_samesite  # type: ignore[assignment]
