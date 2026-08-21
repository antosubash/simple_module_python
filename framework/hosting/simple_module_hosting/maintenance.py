"""Maintenance mode — serve everyone but admins a 503 page.

Sits late in the pipeline, after auth (so it knows who is asking), after
locale (so the page is translated) and after the Inertia shared-props
middleware (so the page keeps its layout instead of rendering bare).

Admins pass through. That is the whole point: someone has to be able to reach
the settings screen and turn it back off. For the same reason the auth
provider's own routes stay open — an admin who is signed *out* when the switch
is flipped must still be able to sign in.
"""

from __future__ import annotations

import logging

from simple_module_core.permissions import is_admin
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Kept reachable while the gate is closed: liveness probes (so orchestrators
# do not kill the pod mid-maintenance), static assets and i18n bundles (or the
# 503 page renders unstyled and untranslated).
_ALWAYS_OPEN_PREFIXES = (
    "/health",
    "/static/",
    "/i18n/",
)

__all__ = ["MaintenanceMiddleware"]


class MaintenanceMiddleware:
    """Short-circuit non-admin traffic with a 503 while maintenance is on."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._host_settings(scope)
        if settings is None or not getattr(settings, "maintenance_mode", False):
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        if any(path.startswith(p) for p in _ALWAYS_OPEN_PREFIXES):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if self._may_bypass(request, scope):
            await self.app(scope, receive, send)
            return

        # Distinguishes "we took the site down on purpose" from the generic
        # 503 the page would otherwise show. The page needs the flag because
        # the operator's message is optional — without it there would be
        # nothing to say beyond "service unavailable".
        request.state.maintenance = True
        message = getattr(settings, "maintenance_message", "") or ""
        response = await self._render(request, message)
        await response(scope, receive, send)

    @staticmethod
    def _host_settings(scope: Scope):
        host_state = getattr(scope["app"].state, "host", None)
        return getattr(host_state, "settings", None)

    @staticmethod
    def _may_bypass(request: Request, scope: Scope) -> bool:
        """Admins, and anyone heading for the auth provider's own routes."""
        user = getattr(request.state, "user", None)
        if user is not None and is_admin(getattr(user, "roles", None)):
            return True

        # An admin locked out by the switch still needs the login flow. Ask the
        # provider which paths those are rather than hardcoding a module's URLs.
        auth_state = getattr(scope["app"].state, "auth", None)
        provider = getattr(auth_state, "auth_provider", None)
        if provider is None:
            return False
        try:
            prefix_paths, exact_paths = provider.get_public_paths()
        except Exception:
            logger.exception("Auth provider failed to report public paths")
            return False
        path: str = scope["path"]
        return any(path.startswith(p) for p in prefix_paths) or path in exact_paths

    @staticmethod
    async def _render(request: Request, message: str):
        # Imported here rather than at module scope: _error_handlers imports
        # from inertia, and a circular import at boot is a worse failure than
        # a per-request attribute lookup.
        from simple_module_hosting._error_handlers import _wants_json, render_error_page

        if _wants_json(request):
            return JSONResponse(
                status_code=503,
                content={"detail": message or "Service temporarily unavailable"},
                headers={"Retry-After": "3600"},
            )
        response = await render_error_page(request, 503, message)
        response.headers["Retry-After"] = "3600"
        return response
