"""Tenants errors and their HTTP mapping."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from simple_module_db import MissingTenantError, TenantIsolationError

from tenants.contracts.entitlements import EntitlementExceededError

logger = logging.getLogger(__name__)

_INDEX_URL = "/tenants/"


class TenantError(Exception):
    """A rejected tenant operation. ``code`` is a stable, translatable key."""

    def __init__(self, code: str, *, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


async def _tenant_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, TenantError)
    return JSONResponse({"detail": exc.code}, status_code=exc.status_code)


async def _entitlement_exceeded(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, EntitlementExceededError)
    return JSONResponse(
        {"detail": "plan_limit", "key": exc.key, "limit": exc.limit}, status_code=402
    )


async def _isolation_error(request: Request, exc: Exception) -> Response:
    """A tenant isolation rule fired during a request.

    Only a *missing* tenant for a signed-in user is a user state — no
    organisation yet, or theirs is suspended — and gets the picker instead of
    a 500. Anything else (a cross-tenant write, a tenant_id change) is a bug
    or an attack: refused with 403 and logged as an error, never dressed up
    as "pick an organisation".
    """
    user = getattr(request.state, "user", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    if not isinstance(exc, MissingTenantError) or tenant_id is not None or user is None:
        logger.error(
            "Tenant isolation violation on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse({"detail": "tenant_isolation"}, status_code=403)
    if _is_api(request) or request.method not in ("GET", "HEAD"):
        return JSONResponse({"detail": "tenant_required"}, status_code=403)
    return RedirectResponse(f"{_INDEX_URL}?reason=tenant_required", status_code=303)


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TenantError, _tenant_error)
    app.add_exception_handler(EntitlementExceededError, _entitlement_exceeded)
    app.add_exception_handler(TenantIsolationError, _isolation_error)
