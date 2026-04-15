"""Auth middleware — redirects unauthenticated requests, refreshes tokens.

Uses the raw ASGI middleware pattern instead of ``BaseHTTPMiddleware``
to avoid its known issues with streaming responses, extra task creation,
and ``ContextVar`` propagation.
"""

from __future__ import annotations

import logging

from simple_module_db.listeners import current_user_id
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from auth.contracts.schemas import UserContext

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = (
    "/auth/",
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    # users module — all API routes let through so RequiresPermission handles
    # auth enforcement (returns 401/403) rather than a page redirect (302).
    "/api/users/",
    # Users module public view routes (Task 7). These render the login /
    # register / password-reset / verify pages; they must be reachable
    # before the user has a session.
    "/users/login",
    "/users/register",
    "/users/forgot-password",
    "/users/reset-password",
    "/users/verify",
    "/users/invite/accept",
)
EXACT_PUBLIC_PATHS = ("/",)


class AuthMiddleware:
    """Redirect unauthenticated users to Keycloak login.

    Sets ``request.state.user`` for downstream handlers.
    Also sets the ``current_user_id`` context var for DB audit listeners.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        is_public = any(path.startswith(p) for p in PUBLIC_PATHS) or path in EXACT_PUBLIC_PATHS

        # SessionMiddleware must be installed upstream; accessing scope["session"]
        # directly ensures misconfiguration raises loudly instead of silently
        # discarding the "next" URL on the redirect branch below.
        session = scope["session"]
        userinfo = session.get("userinfo")

        if not userinfo and not is_public:
            # Protected path without session — redirect to login
            request = Request(scope)
            session["next"] = str(request.url)
            response = RedirectResponse("/auth/login", status_code=302)
            await response(scope, receive, send)
            return

        if userinfo:
            # Set user context on request state (for both public and protected paths)
            user = UserContext.from_keycloak_userinfo(userinfo)
            request = Request(scope)
            request.state.user = user

            # Set context var for DB audit listeners
            token = current_user_id.set(user.id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
            return

        await self.app(scope, receive, send)
