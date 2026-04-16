"""Middleware: security headers, tenant isolation, correlation IDs, request logging, layout data.

All middleware classes use the raw ASGI pattern instead of ``BaseHTTPMiddleware``
to avoid its known issues with streaming responses, extra task creation,
and ``ContextVar`` propagation.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import TYPE_CHECKING

from simple_module_db import current_tenant_id
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_hosting._inertia_shared import build_i18n_block
from simple_module_hosting.csrf import SESSION_CSRF_TOKEN_KEY
from simple_module_hosting.logging import correlation_id
from simple_module_hosting.permissions import expand_permissions, resolve_permissions

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

_request_logger = logging.getLogger("simple_module.request")
logger = logging.getLogger(__name__)

# Paths that produce noisy, low-value log entries
_QUIET_PREFIXES = ("/health", "/static/")


class CorrelationIdMiddleware:
    """Generate or propagate a correlation ID for every request.

    Reads the incoming ``X-Correlation-ID`` header (or generates a UUID4) and
    stores it in a :class:`~contextvars.ContextVar` so that every log record
    emitted during the request automatically includes the ID.  The same value
    is echoed back in the response header.
    """

    HEADER = "X-Correlation-ID"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid = Headers(scope=scope).get(self.HEADER) or uuid.uuid4().hex

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[self.HEADER] = cid
            await send(message)

        token = correlation_id.set(cid)
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id.reset(token)


class RequestLoggingMiddleware:
    """Log every request/response pair with timing and status information."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if any(path.startswith(p) for p in _QUIET_PREFIXES):
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        _request_logger.debug(
            "request.started",
            extra={"method": method, "path": path, "client_ip": client_ip},
        )

        status_code: int | None = None
        start = time.perf_counter()

        async def send_capture(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_capture)
        finally:
            # Log completion even when the inner app raises, so 500s are observable.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _request_logger.info(
                "request.completed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )


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
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    _DEFAULT_HSTS = "max-age=31536000; includeSubDomains"

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
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "SAMEORIGIN"
                headers["X-XSS-Protection"] = "1; mode=block"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                if self.csp:
                    headers["Content-Security-Policy"] = self.csp
                if self.hsts:
                    headers["Strict-Transport-Security"] = self.hsts
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
        if scope["type"] != "http":
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
    """Inject shared data (auth, menus, CSRF) into every Inertia response.

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
        if scope["type"] != "http":
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

        # Session-scoped CSRF token — minted once per session, reused until
        # the session is cleared (logout, session-fixation rotate, etc.).
        # Embedded in shared props so the frontend can echo it back in the
        # ``X-CSRF-Token`` header on every unsafe request (see CSRFMiddleware).
        session = scope.get("session")
        csrf_token = ""
        if session is not None:
            csrf_token = session.get(SESSION_CSRF_TOKEN_KEY) or ""
            if not csrf_token:
                csrf_token = secrets.token_urlsafe(32)
                session[SESSION_CSRF_TOKEN_KEY] = csrf_token

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
            SESSION_CSRF_TOKEN_KEY: csrf_token,
            "i18n": i18n_block,
        }
        request.state.inertia_shared = shared

        await self.app(scope, receive, send)
