"""Finalize last-resort routes after hosts have finished composing the app."""

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send


def mark_fallback_routes(app: FastAPI, start: int) -> None:
    """Mark the actual entries added by an include, including lazy router entries."""
    for route in app.routes[start:]:
        route._sm_fallback = True
    if not getattr(app.state, "fallback_routes_registered", False):
        app.add_middleware(_FinalizeFallbackRoutes, host=app)
        app.state.fallback_routes_registered = True


def finalize_fallback_routes(app: FastAPI) -> None:
    """Keep ordinary routes, mount redirects, then fallbacks, each in stable order."""
    if not getattr(app.state, "fallback_routes_registered", False):
        return
    ordinary, fallbacks = [], []
    for route in app.routes:
        if isinstance(route, _MountRedirect):
            continue
        target = fallbacks if getattr(route, "_sm_fallback", False) else ordinary
        target.append(route)
    # Starlette only attempts slash redirects after *all* routes fail to match.
    redirects = []
    if app.router.redirect_slashes:
        redirects = [
            _MountRedirect(route.path)
            for route in ordinary
            if isinstance(route, Mount) and route.path
        ]
    app.router.routes[:] = ordinary + redirects + fallbacks


class _MountRedirect(Route):
    def __init__(self, path: str) -> None:
        super().__init__(path, self.redirect, include_in_schema=False)
        self.methods = None  # Mount slash redirects apply to every HTTP method.

    async def redirect(self, request: Request) -> RedirectResponse:
        return RedirectResponse(request.url.replace(path=f"{request.url.path}/"))


class _FinalizeFallbackRoutes:
    """Also finalize before dispatch when an ASGI client skips lifespan."""

    def __init__(self, app: ASGIApp, host: FastAPI) -> None:
        self.app = app
        self.host = host
        self.finalized = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.finalized and scope["type"] in {"http", "websocket"}:
            finalize_fallback_routes(self.host)
            self.finalized = True
        await self.app(scope, receive, send)
