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

from sm_auth.contracts.schemas import UserContext

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = ("/auth/", "/health", "/static/", "/api/docs", "/api/redoc", "/openapi.json")
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

        # Skip public paths
        path = scope["path"]
        if any(path.startswith(p) for p in PUBLIC_PATHS) or path in EXACT_PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # Check session for user info (set by SessionMiddleware)
        session = scope.get("session", {})
        userinfo = session.get("userinfo")
        if not userinfo:
            # Store the original URL to redirect back after login
            request = Request(scope)
            session["next"] = str(request.url)
            response = RedirectResponse("/auth/login", status_code=302)
            await response(scope, receive, send)
            return

        # TODO: Check access_token expiry and refresh if needed
        # For now, trust the session is valid

        # Set user context on request state
        user = UserContext.from_keycloak_userinfo(userinfo)
        request = Request(scope)
        request.state.user = user

        # Set context var for DB audit listeners
        token = current_user_id.set(user.id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_id.reset(token)
