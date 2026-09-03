"""UsersAuthProvider — AuthProvider implementation for the users module.

Resolves users from session cookies (browser) or the principal-resolver chain
(bearer tokens, PATs). Session handling mirrors the original AuthMiddleware
logic: fast path from ``session["user_ctx"]``, slow path via DB lookup.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod

from auth.contracts.schemas import UserContext
from starlette.requests import Request

logger = logging.getLogger(__name__)

_SESSION_USER_ID_KEY = "user_id"
_SESSION_USER_CTX_KEY = "user_ctx"
_SESSION_VERSION_KEY = "session_version"
# Mirrors ``simple_module_hosting.session.SESSION_REMEMBER_KEY``. Duplicated as
# a literal for the same reason as the keys above: this module reads the raw
# session dict and does not import the framework's middleware.
_SESSION_REMEMBER_KEY = "remember"


def _stamped_version(session) -> int:
    """The revocation counter this session was minted under.

    Missing or unreadable means 0 — the value every session predating the
    column carries, and the default on the row, so upgrading signs nobody out.
    """
    try:
        return int(session.get(_SESSION_VERSION_KEY, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _forget(session) -> None:
    """Drop everything this session claimed about who is signed in."""
    session.pop(_SESSION_USER_ID_KEY, None)
    session.pop(_SESSION_USER_CTX_KEY, None)
    session.pop(_SESSION_VERSION_KEY, None)
    # "Keep me signed in" was a choice about *this* sign-in. Leaving it behind
    # would hand a 30-day cookie to the anonymous session that replaces it.
    session.pop(_SESSION_REMEMBER_KEY, None)


class UsersAuthProvider:
    """Cookie + bearer auth provider using fastapi-users' DatabaseStrategy."""

    name = "users"
    _is_auth_provider = True

    async def resolve_user(self, request: Request) -> UserContext | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request.scope, auth_header[7:])

        session = request.scope.get("session", {})
        raw_user_id = session.get(_SESSION_USER_ID_KEY)
        if not raw_user_id:
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

    async def _version_still_current(self, scope, user_id: uuid_mod.UUID, session) -> bool:
        """Whether this session predates the account's last "sign out everywhere".

        A user row that has vanished answers False: the account is gone, so
        the cached context describes nobody.
        """
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
            # an app that is merely having a bad minute.
            logger.exception("Session version check failed for %s; keeping the session", user_id)
            return True
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

            from users.models import User, UserAccessToken

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                stmt = select(UserAccessToken).where(UserAccessToken.token == token)
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
