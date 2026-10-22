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

from simple_module_core.cors import CorsPolicy, CorsPolicyRegistry
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting.host_settings import HostSettings


def host_policy(settings: HostSettings) -> CorsPolicy | None:
    """The ``/api/`` policy from ``cors_*`` settings; ``None`` when no origin is set."""
    # Every field is read even when unset: they are restart-required, and the
    # build-time-settings guard learns that from the reads.
    fields = (
        settings.cors_allow_origins,
        settings.cors_allow_credentials,
        settings.cors_allow_methods,
        settings.cors_allow_headers,
        settings.cors_expose_headers,
        settings.cors_max_age,
    )
    origins, credentials, methods, headers, expose, max_age = fields
    if not origins:
        return None
    return CorsPolicy(
        origins=tuple(origins),
        allow_credentials=credentials,
        methods=tuple(methods),
        headers=tuple(headers),
        expose_headers=tuple(expose),
        max_age=max_age,
    )


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
            self._handlers[policy] = handler
        return handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or len(self.registry) == 0:
            await self.app(scope, receive, send)
            return
        policy = self.registry.match(scope["method"], scope["path"])
        if policy is None:
            await self.app(scope, receive, send)
            return
        await self._handler(policy)(scope, receive, send)
