"""Tenant-context middleware: which tenant a request acts for."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from simple_module_db import current_tenant_id, is_valid_tenant_id
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

_SCOPE_HTTP = "http"

TENANT_HEADER = "X-Tenant-ID"


TenantResolver = Callable[[Request], Awaitable[str | None]]
"""Module-owned tenant resolution, registered as ``app.state.tenant_resolver``.

Returns the tenant the request acts for, or ``None``. It owns *every* source —
membership, session, subdomain, header — so it is also where each is
validated. Without one the middleware falls back to the principal's
``tenant_id`` claim."""


class TenantMiddleware:
    """Establish the request's tenant context.

    Sets the ``current_tenant_id`` context var so that DB queries on
    :class:`~simple_module_db.mixins.MultiTenantMixin` models are
    automatically filtered, and new objects get ``tenant_id`` populated.

    Also stores the resolved value on ``request.state.tenant_id``.

    Resolution:

    1. If a module registered ``app.state.tenant_resolver`` (the ``tenants``
       module does), its answer is final — including ``None``.
    2. Otherwise the authenticated user's ``tenant_id`` attribute (from the
       auth token claims).
    3. Otherwise, for **anonymous** requests only, the configured header —
       useful for API clients and tests. Pass ``header=None`` (the default)
       to disable it. An authenticated user is never allowed to pick a tenant
       by header: a user with no tenant of their own would otherwise be able
       to name anyone's.
    """

    def __init__(
        self, app: ASGIApp, *, header: str | None = None, fixed: str | None = None
    ) -> None:
        self.app = app
        self.header = header
        # Single-tenant hosts: one tenant for every request, nothing resolved.
        self.fixed = fixed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        tenant_id = await self._resolve(request, scope)
        request.state.tenant_id = tenant_id

        if tenant_id is not None:
            token = current_tenant_id.set(tenant_id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_tenant_id.reset(token)
            return

        await self.app(scope, receive, send)

    async def _resolve(self, request: Request, scope: Scope) -> str | None:
        if self.fixed is not None:
            return self.fixed
        app = scope.get("app")
        resolver: TenantResolver | None = getattr(
            getattr(app, "state", None), "tenant_resolver", None
        )
        if resolver is not None:
            return await resolver(request)

        user = getattr(request.state, "user", None)
        if user is not None:
            return getattr(user, "tenant_id", None)

        if self.header:
            value = Headers(scope=scope).get(self.header)
            # Unvalidated, an over-long value is a 500 on the first stamped
            # write (VARCHAR(50)) and any junk becomes a tenant name (#366).
            return value if is_valid_tenant_id(value) else None
        return None


__all__ = ["TENANT_HEADER", "TenantMiddleware", "TenantResolver"]
