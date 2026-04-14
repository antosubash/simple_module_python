"""Middleware for security headers, correlation IDs, request logging, and Inertia layout data."""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from simple_module_hosting.logging import correlation_id
from simple_module_hosting.permissions import expand_permissions, resolve_permissions

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

_request_logger = logging.getLogger("simple_module.request")

# Paths that produce noisy, low-value log entries
_QUIET_PREFIXES = ("/health", "/static/")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Generate or propagate a correlation ID for every request.

    Reads the incoming ``X-Correlation-ID`` header (or generates a UUID4) and
    stores it in a :class:`~contextvars.ContextVar` so that every log record
    emitted during the request automatically includes the ID.  The same value
    is echoed back in the response header.
    """

    HEADER = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(self.HEADER) or uuid.uuid4().hex
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
            response.headers[self.HEADER] = cid
            return response
        finally:
            correlation_id.reset(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request/response pair with timing and status information."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in _QUIET_PREFIXES):
            return await call_next(request)

        method = request.method
        client_ip = request.client.host if request.client else "unknown"

        _request_logger.debug(
            "request.started",
            extra={"method": method, "path": path, "client_ip": client_ip},
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        _request_logger.info(
            "request.completed",
            extra={
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class InertiaLayoutDataMiddleware(BaseHTTPMiddleware):
    """Inject shared data (auth, menus, CSRF) into every Inertia response.

    This middleware reads the user from ``request.state.user`` (set by auth middleware)
    and populates ``request.state.inertia_shared`` for the Inertia render function.
    """

    def __init__(
        self,
        app: object,
        menu_registry: MenuRegistry,
        permission_registry: PermissionRegistry,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        self.menu_registry = menu_registry
        self.permission_registry = permission_registry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user = getattr(request.state, "user", None)
        is_authenticated = user is not None
        roles = getattr(user, "roles", []) if user else []

        # Resolve permissions once and cache on request.state for RequiresPermission
        resolved = resolve_permissions(roles) if is_authenticated else set()
        request.state.resolved_permissions = resolved

        # Expand wildcard to full list for frontend (no "*" leak)
        all_perms = self.permission_registry.all_permissions
        frontend_permissions = expand_permissions(resolved, all_perms) if is_authenticated else []

        shared: dict = {
            "auth": {
                "user": (
                    {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "roles": user.roles,
                    }
                    if user
                    else None
                ),
                "isAuthenticated": is_authenticated,
                "permissions": frontend_permissions,
            },
            "menus": self.menu_registry.get_for_user(
                is_authenticated=is_authenticated,
                roles=roles,
            ),
            "csrf_token": secrets.token_urlsafe(32) if is_authenticated else "",
        }
        request.state.inertia_shared = shared

        return await call_next(request)
