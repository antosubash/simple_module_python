"""Tenant-context middleware: which tenant a request acts for."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

from simple_module_db import current_tenant_id, is_valid_tenant_id
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

_SCOPE_HTTP = "http"

TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True, slots=True)
class TenantResolution:
    """A resolver's answer plus how it got there.

    ``source`` is what ends up on ``request.state.tenant_source`` (``"subdomain"``,
    ``"header"``, ``"session"``, ...). ``vary`` names the request headers the
    answer depended on (``"Host"``, the tenant header); the middleware adds them
    to the response ``Vary`` so a shared cache cannot hand one tenant's response
    to another. Report a header even when the answer is ``None``: its absence
    was an input too.
    """

    tenant_id: str | None
    source: str | None = None
    vary: tuple[str, ...] = ()


TenantResolver = Callable[[Request], Awaitable["str | TenantResolution | tuple | None"]]
"""Module-owned tenant resolution, registered as ``app.state.tenant_resolver``.

Returns the tenant the request acts for, or ``None``. It owns *every* source —
membership, session, subdomain, header — so it is also where each is
validated. Without one the middleware falls back to the principal's
``tenant_id`` claim.

A plain ``str | None`` still works (the source is recorded as ``"resolver"``).
Return a :class:`TenantResolution` (or a ``(tenant_id, source)`` pair) to
report the source and the headers consulted."""


def _normalise(result: object) -> TenantResolution:
    if isinstance(result, TenantResolution):
        return result
    if isinstance(result, tuple):
        tenant_id, source = result[0], (result[1] if len(result) > 1 else None)
        return TenantResolution(tenant_id, source if tenant_id is not None else None)
    return TenantResolution(result, "resolver" if result is not None else None)  # type: ignore[arg-type]


def merge_vary(existing: str | None, names: tuple[str, ...]) -> str | None:
    """``existing`` with ``names`` appended, case-insensitively de-duplicated."""
    present = [v.strip() for v in (existing or "").split(",") if v.strip()]
    if "*" in present:
        return existing
    seen = {v.lower() for v in present}
    for name in names:
        if name.lower() not in seen:
            present.append(name)
            seen.add(name.lower())
    return ", ".join(present) if present else None


class TenantMiddleware:
    """Establish the request's tenant context.

    Sets the ``current_tenant_id`` context var so that DB queries on
    :class:`~simple_module_db.mixins.MultiTenantMixin` models are
    automatically filtered, and new objects get ``tenant_id`` populated.

    Also stores the resolved value on ``request.state.tenant_id`` and where it
    came from on ``request.state.tenant_source`` (``fixed``, ``subdomain``,
    ``header``, ``session``, ``claim``, ``anon_header``, ``resolver`` or ``None``).
    Headers the answer depended on are added to the response ``Vary``.

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
        resolution = await self._resolve(request, scope)
        tenant_id = resolution.tenant_id
        request.state.tenant_id = tenant_id
        request.state.tenant_source = resolution.source

        send = self._vary_sender(send, resolution.vary)
        if tenant_id is not None:
            token = current_tenant_id.set(tenant_id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_tenant_id.reset(token)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _vary_sender(send: Send, vary: tuple[str, ...]) -> Send:
        if not vary:
            return send

        async def wrapped(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                merged = merge_vary(headers.get("vary"), vary)
                if merged is not None:
                    headers["vary"] = merged
            await send(message)

        return wrapped

    async def _resolve(self, request: Request, scope: Scope) -> TenantResolution:
        if self.fixed is not None:
            return TenantResolution(self.fixed, "fixed")
        app = scope.get("app")
        resolver: TenantResolver | None = getattr(
            getattr(app, "state", None), "tenant_resolver", None
        )
        if resolver is not None:
            return _normalise(await resolver(request))

        user = getattr(request.state, "user", None)
        if user is not None:
            claim = getattr(user, "tenant_id", None)
            return TenantResolution(claim, "claim" if claim is not None else None)

        if self.header:
            value = Headers(scope=scope).get(self.header)
            # Unvalidated, an over-long value is a 500 on the first stamped
            # write (VARCHAR(50)) and any junk becomes a tenant name (#366).
            ok = is_valid_tenant_id(value)
            return TenantResolution(
                value if ok else None, "anon_header" if ok else None, (self.header,)
            )
        return TenantResolution(None)


__all__ = [
    "TENANT_HEADER",
    "TenantMiddleware",
    "TenantResolution",
    "TenantResolver",
    "merge_vary",
]
