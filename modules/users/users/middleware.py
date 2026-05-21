"""Local-user auth middleware — replaces the Keycloak session reader.

Reads ``session["user_id"]``, loads the User row with eagerly-loaded roles,
builds a UserContext, and sets ``request.state.user`` + the
``current_user_id`` ContextVar consumed by DB audit listeners.

The resolved ``UserContext`` is cached in the signed session cookie under
``session["user_ctx"]`` so subsequent requests skip the DB lookup. The cache
is refreshed when the session is cleared (logout / rotation) or when the
cached payload is missing/invalid. Trade-off: admin-side changes (role
assignment, disable/enable) do not take effect until the affected user's
session is recreated (re-login or session expiry); acceptable for this app.

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
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from users.constants import SESSION_USER_ID_KEY
from users.models import User

logger = logging.getLogger(__name__)

SESSION_USER_CTX_KEY = "user_ctx"
_SESSION_USER_ID_KEY = SESSION_USER_ID_KEY
_SESSION_NEXT_KEY = "next"
_SCOPE_HTTP = "http"
_LOGIN_REDIRECT = "/users/login"

# Paths that don't require authentication.
PUBLIC_PATHS = (
    "/users/login",
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

    On cache hit (``session["user_ctx"]`` present), skips the DB entirely.
    On cache miss, loads the user with roles, validates active/enabled, and
    writes the resolved context back to the session.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        is_public = any(path.startswith(p) for p in PUBLIC_PATHS) or path in EXACT_PUBLIC_PATHS

        session = scope["session"]
        raw_user_id = session.get(_SESSION_USER_ID_KEY)

        user_ctx: UserContext | None = None
        if raw_user_id:
            user_id_str = str(raw_user_id)
            # Fast path — rebuild from the signed session cookie.
            user_ctx = UserContext.from_session_dict(session.get(SESSION_USER_CTX_KEY))
            if user_ctx is None or user_ctx.id != user_id_str:
                try:
                    user_uuid = uuid.UUID(user_id_str)
                except (ValueError, TypeError):
                    logger.warning("Invalid user_id in session: %r", raw_user_id)
                    session.pop(_SESSION_USER_ID_KEY, None)
                    session.pop(SESSION_USER_CTX_KEY, None)
                    user_ctx = None
                else:
                    user_ctx = await self._load_user(scope, user_uuid)
                    if user_ctx is None:
                        # User was deleted / disabled since session creation.
                        session.pop(_SESSION_USER_ID_KEY, None)
                        session.pop(SESSION_USER_CTX_KEY, None)
                    else:
                        session[SESSION_USER_CTX_KEY] = user_ctx.to_session_dict()

        # Fall-through: registered principal resolvers (PAT, API key, ...).
        # The session-cookie path above is authoritative; resolvers only run
        # when no session-authenticated user was resolved.
        if user_ctx is None:
            auth_state = getattr(scope["app"].state, "auth", None)
            resolvers = getattr(auth_state, "principal_resolvers", ()) if auth_state else ()
            if resolvers:
                request = Request(scope)
                for resolver in resolvers:
                    try:
                        user_ctx = await resolver(request)
                    except Exception:
                        logger.exception(
                            "Principal resolver %r raised; treating as no-match",
                            resolver,
                        )
                        continue
                    if user_ctx is not None:
                        break

        if user_ctx is None and not is_public:
            if path.startswith("/api/"):
                response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            else:
                request = Request(scope)
                session[_SESSION_NEXT_KEY] = str(request.url)
                response = RedirectResponse(_LOGIN_REDIRECT, status_code=302)
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
            session_factory = scope["app"].state.sm.db.session_factory
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
