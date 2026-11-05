"""Middleware: security headers, tenant isolation, Inertia shared-props.

Correlation IDs and request logging live in :mod:`._observability`.

All middleware classes use the raw ASGI pattern instead of ``BaseHTTPMiddleware``
to avoid its known issues with streaming responses, extra task creation,
and ``ContextVar`` propagation.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from simple_module_core.app_state import get_principal_serializer
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting._inertia_shared import (
    build_i18n_block,
    build_menu_translator,
    default_home_url,
    lazy_csrf_shared_prop,
    merge_shared_prop_providers,
)
from simple_module_hosting._observability import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
)
from simple_module_hosting._security_headers import SecurityHeadersMiddleware
from simple_module_hosting._spa_mount import native_prefixes
from simple_module_hosting._tenant import (
    TENANT_HEADER,
    TenantMiddleware,
    TenantResolution,
    TenantResolver,
)
from simple_module_hosting.permissions import expand_permissions, resolve_request_permissions
from simple_module_hosting.token_guard import is_token_principal

if TYPE_CHECKING:
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)

_SCOPE_HTTP = "http"

__all__ = [
    "TENANT_HEADER",
    "CorrelationIdMiddleware",
    "InertiaLayoutDataMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
    "TenantMiddleware",
    "TenantResolution",
    "TenantResolver",
]


PrincipalSerializer = Callable[[Any], dict[str, Any]]
"""Module-owned projection from ``request.state.user`` to the ``auth.user``
shared-prop dict. Framework never inspects user fields beyond ``roles``; a
module (typically ``users``) registers a serializer on ``app.state`` so the
user-schema stays out of the hosting layer."""


class InertiaLayoutDataMiddleware:
    """Inject shared data (auth, menus, i18n) into every Inertia response.

    This middleware reads the user from ``request.state.user`` (set by auth middleware)
    and installs an async factory; page resolution populates
    ``request.state.inertia_shared`` for the Inertia render function.

    The ``auth.user`` projection is produced by a module-registered serializer
    looked up on ``request.app.state.principal_serializer``. Without one,
    ``auth.user`` is ``None`` even when a user is authenticated.
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
        # Resolve permissions once — roles plus module grant sources (GH #337) —
        # and cache on request.state for RequiresPermission and the menu filter.
        # May demote the principal (a credential its account no longer backs).
        resolved = await resolve_request_permissions(request, self.permission_registry)
        user = getattr(request.state, "user", None)

        # Permissions stay eager for route guards; layout work waits for rendering.
        async def build_shared() -> dict:
            if is_token_principal(user):
                return await self._shared(request, scope, None, set())
            return await self._shared(request, scope, user, resolved)

        request.state.inertia_shared_factory = build_shared
        # Resolved later (a page render, or the 500 page after TenantMiddleware
        # has unbound its tenant): run it in the context this middleware saw, so
        # providers see the same tenant and user the eager build used to.
        request.state.inertia_shared_context = contextvars.copy_context()

        await self.app(scope, receive, send)

    async def _shared(self, request: Request, scope: Scope, user: Any, resolved: set[str]) -> dict:
        """The shared props for *user* (``None``: the anonymous visitor)."""
        is_authenticated = user is not None
        roles = getattr(user, "roles", []) if user else []

        # Expand wildcard to full list for frontend (no "*" leak)
        all_perms = self.permission_registry.all_permissions
        frontend_permissions = expand_permissions(resolved, all_perms) if is_authenticated else []

        i18n_block = build_i18n_block(scope, request, is_authenticated=is_authenticated)

        principal_serializer: PrincipalSerializer | None = get_principal_serializer(scope["app"])
        user_payload: dict[str, Any] | None = (
            principal_serializer(user) if user is not None and principal_serializer else None
        )

        shared: dict = {
            "auth": {
                "user": user_payload,
                "isAuthenticated": is_authenticated,
                "permissions": frontend_permissions,
            },
            "menus": await self.menu_registry.get_for_request(
                request,
                is_authenticated=is_authenticated,
                roles=roles,
                # Already expanded above (wildcards resolved), which is exactly
                # what the menu filter needs to drop entries that would 403.
                permissions=frontend_permissions,
                translate=build_menu_translator(request),
            ),
            "i18n": i18n_block,
            **lazy_csrf_shared_prop(request, is_authenticated=is_authenticated),
            "nativePrefixes": native_prefixes(scope["app"]),
        }

        # Merge module-registered shared-prop providers (e.g. branding) — read off
        # app.state without importing the plugin (SM009), defensively. They read
        # ``request.state.user`` themselves, so they see the same principal.
        actual = getattr(request.state, "user", None)
        request.state.user = user
        try:
            await merge_shared_prop_providers(scope["app"], request, shared)
        finally:
            request.state.user = actual
        # After the providers, so a module's own value (users) wins.
        shared.setdefault("homeUrl", default_home_url(scope["app"]))
        return shared
