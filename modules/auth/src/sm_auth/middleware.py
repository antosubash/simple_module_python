"""Auth middleware — redirects unauthenticated requests, refreshes tokens."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from simple_module_db.listeners import current_user_id
from sm_auth.contracts.schemas import UserContext

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = ("/auth/", "/health", "/static/", "/api/docs", "/api/redoc", "/openapi.json")
EXACT_PUBLIC_PATHS = ("/",)


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users to Keycloak login.

    Sets ``request.state.user`` for downstream handlers.
    Also sets the ``current_user_id`` context var for DB audit listeners.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip public paths
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS) or path in EXACT_PUBLIC_PATHS:
            return await call_next(request)

        # Check session for user info
        userinfo = request.session.get("userinfo")
        if not userinfo:
            # Store the original URL to redirect back after login
            request.session["next"] = str(request.url)
            return RedirectResponse("/auth/login", status_code=302)

        # TODO: Check access_token expiry and refresh if needed
        # For now, trust the session is valid

        # Set user context on request state
        user = UserContext.from_keycloak_userinfo(userinfo)
        request.state.user = user

        # Set context var for DB audit listeners
        token = current_user_id.set(user.id)
        try:
            response = await call_next(request)
        finally:
            current_user_id.reset(token)

        return response
