"""Serve the first-run wizard while the install is not yet usable.

A fresh deployment has no administrator, so without this every route either
redirects to a login nobody can pass or fails outright. While any required
:class:`~simple_module_core.setup_steps.SetupStep` reports incomplete, this
redirects to ``/setup``.

Sits inside ``InertiaCache`` in the middleware pipeline so its redirect is
never stored by a cache, and outside ``Maintenance`` — an install that is not
set up has nothing to put into maintenance.
"""

from __future__ import annotations

import logging

from starlette.datastructures import Headers
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

SETUP_PATH = "/setup"

# Paths that must answer during setup. /setup itself for obvious reasons;
# /static because the wizard is a real Inertia page that needs its assets, and
# redirecting them to HTML breaks the page that reports the problem; /health
# because an orchestrator killing the container mid-setup is not helpful.
_EXEMPT_PREFIXES = (SETUP_PATH, "/static", "/health")


class SetupMiddleware:
    """Redirect to the setup wizard until every required step is complete."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path.startswith(_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        starlette_app = scope.get("app")
        registry = getattr(getattr(starlette_app, "state", None), "sm", None)
        registry = getattr(registry, "setup_registry", None)
        # No registry, or no module contributed a step: nothing can gate the
        # app. This is the Keycloak case — identity lives elsewhere, so the
        # local users table is legitimately empty forever.
        if not registry:
            await self.app(scope, receive, send)
            return

        if await registry.is_setup_complete(starlette_app):
            await self.app(scope, receive, send)
            return

        await self._redirect(scope, receive, send)

    async def _redirect(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the browser to the wizard.

        Inertia requests get a 409 with ``X-Inertia-Location`` rather than a
        302: Inertia's client follows a redirect with an XHR and would then
        choke on the wizard's HTML document. The 409 tells it to do a full
        page visit instead.
        """
        headers = Headers(scope=scope)
        if headers.get("x-inertia"):
            response = RedirectResponse(SETUP_PATH, status_code=409)
            response.headers["X-Inertia-Location"] = SETUP_PATH
        else:
            response = RedirectResponse(SETUP_PATH, status_code=302)
        await response(scope, receive, send)
