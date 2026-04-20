"""Middleware: security headers, tenant isolation, Inertia shared-props.

Correlation IDs and request logging live in :mod:`._observability`.

All middleware classes use the raw ASGI pattern instead of ``BaseHTTPMiddleware``
to avoid its known issues with streaming responses, extra task creation,
and ``ContextVar`` propagation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from simple_module_db import current_tenant_id
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_hosting._inertia_shared import build_i18n_block
from simple_module_hosting._observability import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
)
from simple_module_hosting.permissions import expand_permissions, resolve_permissions

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)

_SCOPE_HTTP = "http"
_MSG_RESPONSE_START = "http.response.start"

# Security response header names
_HEADER_X_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options"
_HEADER_X_FRAME_OPTIONS = "X-Frame-Options"
_HEADER_X_XSS_PROTECTION = "X-XSS-Protection"
_HEADER_REFERRER_POLICY = "Referrer-Policy"
_HEADER_CSP = "Content-Security-Policy"
_HEADER_HSTS = "Strict-Transport-Security"

# Security response header values
_XCTO_NOSNIFF = "nosniff"
_XFO_SAMEORIGIN = "SAMEORIGIN"
_XXSS_BLOCK = "1; mode=block"
_REFERRER_STRICT_ORIGIN = "strict-origin-when-cross-origin"

__all__ = [
    "TENANT_HEADER",
    "CorrelationIdMiddleware",
    "InertiaLayoutDataMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
    "TenantMiddleware",
]


class SecurityHeadersMiddleware:
    """Add security headers to every response.

    ``content_security_policy`` and ``strict_transport_security`` accept a
    string to override the defaults, or ``None`` to suppress that header
    (useful in development when Vite's HMR client loads cross-origin scripts,
    or behind plain-HTTP loopbacks where HSTS would lock users out).
    """

    _DEFAULT_CSP = (
        "default-src 'self'; "
        # Inertia embeds the initial page blob inline; Vite injects a React
        # Refresh shim at boot. Both require 'unsafe-inline' for scripts.
        # Production builds compile to hashed bundles, so this can be
        # tightened with a nonce once Vite's preamble is removed in prod.
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "script-src-elem 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    _DEFAULT_HSTS = "max-age=31536000; includeSubDomains"

    @staticmethod
    def dev_csp(vite_dev_url: str) -> str:
        """Build a dev CSP that whitelists the Vite dev server.

        In development the browser fetches ``@vite/client``, ``main.tsx``, and
        React Refresh from the Vite origin (default ``http://localhost:5050``),
        and opens a WebSocket there for HMR. Those fail under the prod CSP,
        so we widen ``script-src*``/``connect-src``/``style-src`` for that
        origin only (including the ``ws://`` equivalent for HMR).
        """
        ws_url = vite_dev_url.replace("http://", "ws://").replace("https://", "wss://")
        return (
            "default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {vite_dev_url}; "
            f"script-src-elem 'self' 'unsafe-inline' {vite_dev_url}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {vite_dev_url}; "
            "img-src 'self' data: blob:; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            f"connect-src 'self' {vite_dev_url} {ws_url}; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    def __init__(
        self,
        app: ASGIApp,
        *,
        content_security_policy: str | None = _DEFAULT_CSP,
        strict_transport_security: str | None = _DEFAULT_HSTS,
    ) -> None:
        self.app = app
        self.csp = content_security_policy
        self.hsts = strict_transport_security

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == _MSG_RESPONSE_START:
                headers = MutableHeaders(scope=message)
                headers[_HEADER_X_CONTENT_TYPE_OPTIONS] = _XCTO_NOSNIFF
                headers[_HEADER_X_FRAME_OPTIONS] = _XFO_SAMEORIGIN
                headers[_HEADER_X_XSS_PROTECTION] = _XXSS_BLOCK
                headers[_HEADER_REFERRER_POLICY] = _REFERRER_STRICT_ORIGIN
                if self.csp:
                    headers[_HEADER_CSP] = self.csp
                if self.hsts:
                    headers[_HEADER_HSTS] = self.hsts
            await send(message)

        await self.app(scope, receive, send_with_headers)


TENANT_HEADER = "X-Tenant-ID"


class TenantMiddleware:
    """Extract tenant context from authenticated user or request header.

    Sets the ``current_tenant_id`` context var so that DB queries on
    :class:`~simple_module_db.mixins.MultiTenantMixin` models are
    automatically filtered, and new objects get ``tenant_id`` populated.

    Also stores the resolved value on ``request.state.tenant_id``.

    Tenant is resolved from (in priority order):

    1. Authenticated user's ``tenant_id`` attribute (from auth token claims).
    2. The configured request header, if any — useful for API clients
       and tests. Pass ``header=None`` (the default) to disable the
       header source and force tenant resolution through the auth token
       only. Pass the header name (e.g. ``"X-Tenant-ID"``) to enable.
    """

    def __init__(self, app: ASGIApp, *, header: str | None = None) -> None:
        self.app = app
        self.header = header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        tenant_id: str | None = None

        user = getattr(request.state, "user", None)
        if user is not None:
            tenant_id = getattr(user, "tenant_id", None)

        if tenant_id is None and self.header:
            header_value = Headers(scope=scope).get(self.header)
            if header_value:
                tenant_id = header_value

        request.state.tenant_id = tenant_id

        if tenant_id is not None:
            token = current_tenant_id.set(tenant_id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_tenant_id.reset(token)
            return

        await self.app(scope, receive, send)


class InertiaLayoutDataMiddleware:
    """Inject shared data (auth, menus, i18n) into every Inertia response.

    This middleware reads the user from ``request.state.user`` (set by auth middleware)
    and populates ``request.state.inertia_shared`` for the Inertia render function.
    """

    def __init__(
        self,
        app: ASGIApp,
        menu_registry: MenuRegistry,
        permission_registry: PermissionRegistry,
    ) -> None:
        self.app = app
        self.menu_registry = menu_registry
        self.permission_registry = permission_registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        user = getattr(request.state, "user", None)
        is_authenticated = user is not None
        roles = getattr(user, "roles", []) if user else []

        # Resolve permissions once and cache on request.state for RequiresPermission
        resolved = (
            resolve_permissions(roles, role_map=self.permission_registry.role_map)
            if is_authenticated
            else set()
        )
        request.state.resolved_permissions = resolved

        # Expand wildcard to full list for frontend (no "*" leak)
        all_perms = self.permission_registry.all_permissions
        frontend_permissions = expand_permissions(resolved, all_perms) if is_authenticated else []

        i18n_block = build_i18n_block(scope, request)

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
            "i18n": i18n_block,
        }
        request.state.inertia_shared = shared

        await self.app(scope, receive, send)
