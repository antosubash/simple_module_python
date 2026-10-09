"""The host's tenancy, for modules, without reading the middleware stack (#418).

Use ``require_tenant()`` as a router dependency on any surface that reads or
writes ``MultiTenantMixin`` tables. List it **before** ``get_db``: yield
dependencies exit in reverse order, and the session's commit has to run while
the tenant is still bound.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import HTTPException, Request
from simple_module_core.tenancy import TenancyMode
from simple_module_db import DEFAULT_TENANT_ID, is_valid_tenant_id, tenant_context

__all__ = [
    "TenancyMode",
    "mode_for",
    "require_tenant",
    "single_tenant_id",
    "tenancy_mode",
    "tenant_vary",
]


def mode_for(settings: Any) -> TenancyMode:
    """The mode ``create_app`` builds for ``settings`` — the one place it is decided."""
    return TenancyMode.MULTI if getattr(settings, "multi_tenant", False) else TenancyMode.SINGLE


def tenancy_mode(app: Any) -> TenancyMode:
    """Whether ``app`` scopes requests to tenants.

    ``SINGLE`` for an app built outside ``create_app``.
    """
    sm = getattr(app.state, "sm", None)
    return getattr(sm, "tenancy", TenancyMode.SINGLE)


def single_tenant_id(app: Any) -> str:
    """The tenant every request of a single-tenant host runs in.

    ``default_tenant`` when set, else ``DEFAULT_TENANT_ID`` (``"default"``).
    """
    sm = getattr(app.state, "sm", None)
    db = getattr(sm, "db", None)
    return getattr(db, "default_tenant_id", None) or DEFAULT_TENANT_ID


def tenant_vary(request: Request) -> tuple[str, ...]:
    """Request headers the resolved tenant depended on.

    For routes that set their own cache headers; ``()`` when none were recorded.
    """
    return tuple(getattr(request.state, "tenant_vary", ()) or ())


def require_tenant(
    *,
    on_missing: int | Callable[[Request], Exception] = 403,
    detail: str = "tenant_required",
) -> Callable[[Request], AsyncIterator[str]]:
    """FastAPI yield-dependency that binds the request's tenant for the rest of the request.

    On a single-tenant host it binds :func:`single_tenant_id`, so the route
    works with or without ``TenantMiddleware``. On a multi-tenant host it binds
    what the middleware resolved, and with nothing resolved raises
    ``HTTPException(on_missing, detail)`` — or ``on_missing(request)`` when that
    is a callable, for a surface that should answer, say, 404 instead.

    It is an *async* generator on purpose: a sync generator dependency runs in
    a threadpool, and the contextvar it set would never reach the endpoint.
    """

    async def dependency(request: Request) -> AsyncIterator[str]:
        if tenancy_mode(request.app) is TenancyMode.SINGLE:
            tenant = single_tenant_id(request.app)
        else:
            tenant = getattr(request.state, "tenant_id", None)
            if tenant is None or not is_valid_tenant_id(tenant):
                if isinstance(on_missing, int):
                    raise HTTPException(status_code=on_missing, detail=detail)
                raise on_missing(request)
        with tenant_context(tenant):
            yield tenant

    return dependency
