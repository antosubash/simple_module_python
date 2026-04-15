"""Local-user auth middleware — replaces the Keycloak session reader.

Reads ``session["user_id"]``, loads the User row with eagerly-loaded roles,
builds a UserContext, and sets ``request.state.user`` + the
``current_user_id`` ContextVar consumed by DB audit listeners.

Registered via ``UsersModule.register_middleware``.
"""

from __future__ import annotations

import logging
import uuid

from auth.contracts.schemas import UserContext
from simple_module_db.listeners import current_user_id
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from users.models import User

logger = logging.getLogger(__name__)

# Paths that don't require authentication.
PUBLIC_PATHS = (
    "/users/login",
    "/users/logout",
    "/users/register",
    "/users/forgot-password",
    "/users/reset-password",
    "/users/verify",
    "/users/invite/accept",
    "/api/users/auth/",
    "/api/users/register",
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/i18n/",
)
EXACT_PUBLIC_PATHS = ("/",)


class AuthMiddleware:
    """Redirect unauthenticated users to /users/login.

    Loads the authenticated user from DB on every request. Sets
    ``request.state.user`` and the ``current_user_id`` ContextVar so audit
    listeners stamp created_by / updated_by correctly.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        is_public = any(path.startswith(p) for p in PUBLIC_PATHS) or path in EXACT_PUBLIC_PATHS

        session = scope["session"]
        raw_user_id = session.get("user_id")

        user_ctx: UserContext | None = None
        if raw_user_id:
            try:
                user_uuid = uuid.UUID(raw_user_id)
            except (ValueError, TypeError):
                logger.warning("Invalid user_id in session: %r", raw_user_id)
                session.pop("user_id", None)
            else:
                user_ctx = await self._load_user(scope, user_uuid)
                if user_ctx is None:
                    # User was deleted / disabled since session creation.
                    session.pop("user_id", None)

        if user_ctx is None and not is_public:
            request = Request(scope)
            session["next"] = str(request.url)
            response = RedirectResponse("/users/login", status_code=302)
            await response(scope, receive, send)
            return

        if user_ctx is not None:
            request = Request(scope)
            request.state.user = user_ctx
            token = current_user_id.set(user_ctx.id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
            return

        await self.app(scope, receive, send)

    async def _load_user(self, scope: Scope, user_id: uuid.UUID) -> UserContext | None:
        """Open a fresh session from app.state.db and load the User + roles.

        Returns a UserContext, or None if the user doesn't exist or is
        disabled/inactive. The session is closed on exit; we never commit
        (read-only).
        """
        try:
            session_factory = scope["app"].state.db.session_factory
            async with session_factory() as db_session:
                stmt = select(User).where(User.id == user_id).options(selectinload(User.roles))
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None:
                    return None
                if not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception("Failed to load user %s from DB; treating as unauthenticated", user_id)
            return None
