"""CORS dispatch (#527).

One Starlette ``CORSMiddleware`` is built per distinct :class:`CorsPolicy`; each
request is routed to the one whose policy the registry matches for its method and
path (most specific wins). A request no policy covers passes through untouched,
so a path nobody opted in never gains CORS headers.

Installed between RequestLogging and BodyLimit, so a preflight is answered before
auth, rate limit, setup or maintenance can reject it, and a 413 from BodyLimit
still carries the CORS headers the browser needs to read it.
"""

from __future__ import annotations

from simple_module_core.web.cors import CorsPolicy, CorsPolicyRegistry
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting.pipeline._request_policy import host_policy, request_policy  # noqa: F401
from simple_module_hosting.pipeline._route_access import API_PREFIX


class CorsMiddleware:
    def __init__(self, app: ASGIApp, *, registry: CorsPolicyRegistry) -> None:
        self.app = app
        self.registry = registry
        self._handlers: dict[CorsPolicy, ASGIApp] = {}

    def _handler(self, policy: CorsPolicy) -> ASGIApp:
        handler = self._handlers.get(policy)
        if handler is None:
            handler = CORSMiddleware(
                self.app,
                allow_origins=list(policy.origins),
                allow_credentials=policy.allow_credentials,
                allow_methods=list(policy.methods),
                allow_headers=list(policy.headers),
                expose_headers=list(policy.expose_headers),
                max_age=policy.max_age,
            )
            if len(self._handlers) >= 32:
                self._handlers.clear()
            self._handlers[policy] = handler
        return handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        snapshot = request_policy(scope)
        host = snapshot.cors if snapshot is not None else None
        policy = self.registry.match(
            scope["method"], scope["path"], fallback=(API_PREFIX, host) if host else None
        )
        if policy is None:
            await self.app(scope, receive, send)
            return
        await self._handler(policy)(scope, receive, send)
