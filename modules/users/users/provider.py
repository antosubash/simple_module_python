"""UsersAuthProvider — AuthProvider implementation for the users module.

Resolves users from session cookies (browser) or the principal-resolver chain
(bearer tokens, PATs). Session handling mirrors the original AuthMiddleware
logic: fast path from ``session["user_ctx"]``, slow path via DB lookup.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from auth.contracts.schemas import UserContext
from simple_module_hosting.session import (
    SESSION_COOKIE_MAX_AGE,
    SESSION_EXPIRES_AT_KEY,
    SESSION_REMEMBER_KEY,
    SESSION_SIGNATURE_MAX_AGE,
    ensure_session_expiry,
    session_has_expired,
)
from starlette.requests import Request

from users.constants import SESSION_USER_ID_KEY, SESSION_VERSION_KEY

# Re-exported: the cache lives in its own module (see its docstring), but
# ``users.provider`` is where callers reach for it.
from users.session_version_cache import (  # noqa: F401
    SESSION_VERSION_TTL_SECONDS,
    clear_session_version_cache,
    forget_session_version,
    peek_session_version,
    read_session_version,
    store_session_version,
)

logger = logging.getLogger(__name__)

# Not in ``users.constants``: nothing outside this file writes it, and the
# shape it holds is this provider's own caching detail.
_SESSION_USER_CTX_KEY = "user_ctx"


def _stamped_version(session) -> int:
    """The revocation counter this session was minted under.

    Missing or unreadable means 0 — the value every session predating the
    column carries, and the default on the row, so upgrading signs nobody out.
    """
    try:
        return int(session.get(SESSION_VERSION_KEY, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _forget(session) -> None:
    """Drop everything this session claimed about who is signed in."""
    session.pop(SESSION_USER_ID_KEY, None)
    session.pop(_SESSION_USER_CTX_KEY, None)
    session.pop(SESSION_VERSION_KEY, None)
    session.pop(SESSION_EXPIRES_AT_KEY, None)
    # "Keep me signed in" was a choice about *this* sign-in. Leaving it behind
    # would hand a 30-day cookie to the anonymous session that replaces it.
    session.pop(SESSION_REMEMBER_KEY, None)


class UsersAuthProvider:
    """Cookie + bearer auth provider using fastapi-users' DatabaseStrategy."""

    name = "users"
    _is_auth_provider = True

    async def resolve_user(self, request: Request) -> UserContext | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request.scope, auth_header[7:])

        session = request.scope.get("session", {})
        raw_user_id = session.get(SESSION_USER_ID_KEY)
        if not raw_user_id:
            return None

        # Checked before either resolution path, so the cached context and the
        # DB reload are both covered by one line. The signature window is 30
        # days for the whole process — that is what "keep me signed in" needs —
        # so this deadline is the only thing holding an ordinary sign-in to the
        # 14 days it actually asked for.
        #
        # A session minted before deadlines existed carries none. It is stamped
        # here rather than waved through: the stamp cannot outlast the signature
        # window the signer already enforces, so this only ever tightens, and it
        # leaves ``session_has_expired`` free to fail closed on absence.
        ensure_session_expiry(session, self._session_window(request, session))
        if session_has_expired(session):
            _forget(session)
            return None

        user_id_str = str(raw_user_id)

        try:
            user_uuid = uuid_mod.UUID(user_id_str)
        except (ValueError, TypeError):
            logger.warning("Invalid user_id in session: %r", raw_user_id)
            _forget(session)
            return None

        cached = UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))
        if cached is not None and cached.id == user_id_str:
            # The cached context lives in the client's own signed cookie, so
            # the server cannot reach in and delete it. One indexed
            # primary-key read is what makes "Sign out everywhere" actually
            # sign out a browser this process has never seen — the alternative
            # is a button that only logs out the person pressing it.
            if await self._version_still_current(request.scope, user_uuid, session):
                return cached
            _forget(session)
            return None

        user_ctx = await self._load_user(request.scope, user_uuid, session)
        if user_ctx is None:
            _forget(session)
        else:
            session[_SESSION_USER_CTX_KEY] = user_ctx.to_session_dict()
        return user_ctx

    @staticmethod
    def _session_window(request: Request, session: Mapping[str, Any]) -> int:
        """The window a legacy session should be held to, in seconds.

        Mirrors what the cookie writer already does with this session: the
        remembered window if it recorded one, otherwise the ordinary sign-in
        window. Reading it back means a legacy "keep me signed in" session is
        not quietly demoted to fourteen days on the request that stamps it.
        """
        recorded = session.get(SESSION_REMEMBER_KEY)
        if recorded is True:
            return SESSION_SIGNATURE_MAX_AGE
        # ``bool`` is an ``int``: False means "not remembered", not zero seconds.
        if not isinstance(recorded, bool) and isinstance(recorded, int) and recorded > 0:
            return recorded
        settings = getattr(getattr(request.app.state, "users", None), "settings", None)
        return getattr(settings, "cookie_max_age_seconds", None) or SESSION_COOKIE_MAX_AGE

    async def _version_still_current(self, scope, user_id: uuid_mod.UUID, session) -> bool:
        """Whether this session predates the account's last "sign out everywhere".

        A user row that has vanished answers False: the account is gone, so
        the cached context describes nobody.

        The stored counter is cached for :data:`SESSION_VERSION_TTL_SECONDS`,
        so a revocation made in another worker can take that long to reach
        this one; the worker that made it invalidates its own entry.

        Note the deliberate asymmetry with :meth:`_load_user`: an unreachable
        database keeps an already-resolved session alive here (a bad minute is
        not evidence of a revocation), while there it refuses to *mint* one —
        failing open on a check and closed on a load.
        """
        hit, cached = read_session_version(user_id)
        if hit:
            return cached is not None and int(cached) == _stamped_version(session)
        try:
            from sqlalchemy import select

            from users.models import User

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                stored = (
                    await db_session.execute(select(User.session_version).where(User.id == user_id))
                ).scalar_one_or_none()
        except Exception:
            # A database that cannot be reached is not evidence of a
            # revocation. Refusing here would log every signed-in user out of
            # an app that is merely having a bad minute. Not cached — the next
            # request should retry rather than inherit the outage.
            logger.exception("Session version check failed for %s; keeping the session", user_id)
            return True
        store_session_version(user_id, stored)
        if stored is None:
            return False
        return int(stored) == _stamped_version(session)

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return "/users/login"

    def get_logout_url(self, request: Request | None) -> str:
        return "/users/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            (
                "/users/login",
                "/users/register",
                "/users/forgot-password",
                "/users/reset-password",
                "/users/verify",
                "/users/invite/accept",
                "/api/users/auth/",
                "/api/users/register",
            ),
            (),
        )

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return request.headers.get("authorization", "").startswith("Bearer ")

    async def _resolve_bearer(self, scope, token: str) -> UserContext | None:
        """Look up an access token in users_access_token and return the user."""
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import noload, selectinload

            from users.backend import _TOKEN_LIFETIME_SECONDS
            from users.models import User, UserAccessToken
            from users.token_strategy import token_is_live

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                # Neither clause is optional: this path bypasses fastapi-users'
                # DatabaseStrategy, which is where a lifetime is normally
                # applied, so without them a row authenticated forever. The
                # ceiling is the same constant the strategy reads with, and
                # ``expires_at`` is the row's own deadline — an ordinary
                # sign-in's fourteen days, or ``/auth/token``'s fifteen
                # minutes, rather than the thirty-day ceiling for all of them.
                now = datetime.now(UTC)
                cutoff = now - timedelta(seconds=_TOKEN_LIFETIME_SECONDS)
                stmt = select(UserAccessToken).where(
                    UserAccessToken.token == token,
                    UserAccessToken.created_at > cutoff,
                    UserAccessToken.expires_at > now,
                )
                access = (await db_session.execute(stmt)).scalar_one_or_none()
                if access is None:
                    return None
                # noload oauth_accounts: lazy="selectin" on the model would
                # otherwise fire an extra query the UserContext never reads.
                stmt = (
                    select(User)
                    .where(User.id == access.user_id)
                    .options(selectinload(User.roles), noload(User.oauth_accounts))
                )
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                # The revocation check the session path has had all along. A
                # password change bumps ``session_version`` and strands every
                # session; without this the bearer tokens minted before it kept
                # working, including any an attacker who knew the old password
                # had already collected. Free here — the row is already loaded.
                if not token_is_live(access, user, now):
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception("Bearer token resolution failed")
            return None

    async def _load_user(self, scope, user_id: uuid_mod.UUID, session=None) -> UserContext | None:
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import noload, selectinload

            from users.models import User

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                # noload oauth_accounts: lazy="selectin" on the model would
                # otherwise fire an extra query the UserContext never reads.
                stmt = (
                    select(User)
                    .where(User.id == user_id)
                    .options(selectinload(User.roles), noload(User.oauth_accounts))
                )
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                # Same revocation check as the cached path, free here because
                # the row is already loaded.
                if session is not None and int(user.session_version or 0) != _stamped_version(
                    session
                ):
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception(
                "Failed to load user %s from DB; treating as unauthenticated",
                user_id,
            )
            return None
