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

        cached = UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))
        if cached is not None and cached.id == user_id_str:
            return cached

        try:
            user_uuid = uuid_mod.UUID(user_id_str)
        except (ValueError, TypeError):
            logger.warning("Invalid user_id in session: %r", raw_user_id)
            session.pop(_SESSION_USER_ID_KEY, None)
            session.pop(_SESSION_USER_CTX_KEY, None)
            return None

        user_ctx = await self._load_user(request.scope, user_uuid)
        if user_ctx is None:
            session.pop(_SESSION_USER_ID_KEY, None)
            session.pop(_SESSION_USER_CTX_KEY, None)
        else:
            session[_SESSION_USER_CTX_KEY] = user_ctx.to_session_dict()
        return user_ctx

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
            from sqlalchemy.orm import selectinload

            from users.models import User, UserAccessToken

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                stmt = select(UserAccessToken).where(UserAccessToken.token == token)
                access = (await db_session.execute(stmt)).scalar_one_or_none()
                if access is None:
                    return None
                stmt = (
                    select(User)
                    .where(User.id == access.user_id)
                    .options(selectinload(User.roles))
                )
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception("Bearer token resolution failed")
            return None

    async def _load_user(self, scope, user_id: uuid_mod.UUID) -> UserContext | None:
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            from users.models import User

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                stmt = (
                    select(User)
                    .where(User.id == user_id)
                    .options(selectinload(User.roles))
                )
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception(
                "Failed to load user %s from DB; treating as unauthenticated",
                user_id,
            )
            return None
