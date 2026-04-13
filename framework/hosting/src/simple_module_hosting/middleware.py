"""Middleware for security headers, tenant isolation, and Inertia layout data."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from simple_module_db.listeners import current_tenant_id
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant context from authenticated user or request header.

    Sets the ``current_tenant_id`` context var so that DB queries on
    :class:`~simple_module_db.mixins.MultiTenantMixin` models are
    automatically filtered, and new objects get ``tenant_id`` populated.

    Also stores the resolved value on ``request.state.tenant_id``.

    Tenant is resolved from (in priority order):

    1. Authenticated user's ``tenant_id`` attribute (from auth token claims).
    2. ``X-Tenant-ID`` request header — useful for API clients and testing.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        tenant_id: str | None = None

        # 1. Try to get tenant from authenticated user (set by auth middleware)
        user = getattr(request.state, "user", None)
        if user is not None:
            tenant_id = getattr(user, "tenant_id", None)

        # 2. Fall back to X-Tenant-ID header (only when token has no tenant)
        if tenant_id is None:
            header_value = request.headers.get("X-Tenant-ID")
            if header_value:
                tenant_id = header_value

        request.state.tenant_id = tenant_id

        if tenant_id is not None:
            token = current_tenant_id.set(tenant_id)
            try:
                response = await call_next(request)
            finally:
                current_tenant_id.reset(token)
            return response

        return await call_next(request)


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

        # Build shared data for Inertia
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
            },
            "menus": self.menu_registry.get_for_user(
                is_authenticated=is_authenticated,
                roles=roles,
            ),
            "csrf_token": secrets.token_urlsafe(32),
        }
        request.state.inertia_shared = shared

        return await call_next(request)
