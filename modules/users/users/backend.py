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

from fastapi import Depends, Request
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import AccessTokenDatabase

from users.db_adapter import get_access_token_db
from users.models import UserAccessToken
from users.token_strategy import ExpiringDatabaseStrategy

if TYPE_CHECKING:
    from users.settings import UsersSettings

_TOKEN_LIFETIME_SECONDS = 60 * 60 * 24 * 30  # 30 days
"""Oldest access-token row the query will even look at — the ceiling, not the norm.

This is the *read* window, and there is only one of it: ``current_user``
resolves its strategy from the shared backend, so it cannot vary per request.
A remembered sign-in writes a row it needs for thirty days, and reading it back
against a fourteen-day window would sign those people out halfway through the
window the checkbox promised.

What bounds an individual credential is its own ``UserAccessToken.expires_at``,
stamped at mint time from whatever that sign-in actually asked for and enforced
by :class:`~users.token_strategy.ExpiringDatabaseStrategy`. The cookie's
``Max-Age`` is browser-enforced only, so it cannot be the bound: a cookie lifted
off disk is replayed without one. Revocation depends on neither window — a
``User.session_version`` bump strands sessions and tokens alike, the latter by
the counter this strategy stamps onto each row.
"""

_DEFAULT_COOKIE_SECONDS = 60 * 60 * 24 * 14  # matches UsersSettings.cookie_max_age_seconds

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


def build_strategy(
    access_token_db: AccessTokenDatabase[UserAccessToken],
    mint_lifetime_seconds: int,
) -> ExpiringDatabaseStrategy:
    """A strategy that mints rows lasting ``mint_lifetime_seconds``.

    The read ceiling stays :data:`_TOKEN_LIFETIME_SECONDS` whatever this
    sign-in asked for: one strategy reads back every row the deployment has
    issued, and narrowing the ceiling to the current window would reject the
    longer-lived rows a remembered sign-in wrote.
    """
    return ExpiringDatabaseStrategy(
        access_token_db,
        read_ceiling_seconds=_TOKEN_LIFETIME_SECONDS,
        mint_lifetime_seconds=mint_lifetime_seconds,
    )


def get_database_strategy(
    request: Request,
    access_token_db: AccessTokenDatabase[UserAccessToken] = Depends(get_access_token_db),
) -> ExpiringDatabaseStrategy:
    """The DI-resolved strategy — mints for the ordinary cookie window.

    ``request.app.state.users`` is absent until ``on_startup`` has run, which is
    also true of every route that could reach this; the fallback keeps a
    half-built app from raising an ``AttributeError`` instead of a clean 401.
    """
    users_state = getattr(request.app.state, "users", None)
    settings = getattr(users_state, "settings", None)
    window = getattr(settings, "cookie_max_age_seconds", None) or _DEFAULT_COOKIE_SECONDS
    return build_strategy(access_token_db, window)


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
