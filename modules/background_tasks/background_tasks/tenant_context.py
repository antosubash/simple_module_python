"""Carry the enqueuing request's tenant into the Celery task that runs later.

A task body runs in a worker with no request, so ``current_tenant_id`` is
unset there — under strict isolation any tenant-scoped query would raise, and
without it the query would read every tenant. The tenant is stamped onto the
message headers at publish time and restored around the task body.

Platform tasks that legitimately span tenants (sweeps, purges) wrap their
work in ``simple_module_db.all_tenants()`` instead.
"""

from __future__ import annotations

import logging
from contextvars import Token
from typing import Any

from simple_module_db import TenantIsolationError, current_tenant_id, is_valid_tenant_id

TENANT_HEADER = "sm_tenant_id"

_log = logging.getLogger(__name__)
_tokens: dict[str, Token[str | None]] = {}


def stamp_tenant(headers: dict[str, Any] | None) -> None:
    """Record the current tenant on an outgoing message (publish side).

    An explicit ``headers={"sm_tenant_id": ...}`` passed to ``send_task`` is
    kept only when no tenant is bound (platform code enqueueing work for a
    tenant) or it names the bound tenant: request code must not be able to
    schedule work as another tenant.
    """
    if headers is None:
        return
    tenant_id = current_tenant_id.get()
    explicit = headers.get(TENANT_HEADER)
    if explicit:
        if not is_valid_tenant_id(explicit):
            raise TenantIsolationError(f"Invalid tenant id on task headers: {explicit!r}")
        if tenant_id is not None and explicit != tenant_id:
            raise TenantIsolationError(
                f"Cannot enqueue a task for tenant '{explicit}' in context of tenant '{tenant_id}'"
            )
        return
    if tenant_id is not None:
        headers[TENANT_HEADER] = tenant_id


def _tenant_of(task: Any) -> str | None:
    request = getattr(task, "request", None)
    if request is None:
        return None
    value = getattr(request, TENANT_HEADER, None)
    if value is None and isinstance(getattr(request, "headers", None), dict):
        value = request.headers.get(TENANT_HEADER)
    if not value:
        return None
    if not is_valid_tenant_id(value):
        # Never run a task body as a malformed tenant; it runs unscoped and,
        # under strict mode, fails closed on its first tenant-scoped query.
        _log.warning("Ignoring invalid tenant id on task message: %r", str(value)[:80])
        return None
    return str(value)


def restore_tenant(*, task_id: str | None, task: Any) -> None:
    """Enter the message's tenant for the task body (prerun)."""
    if not task_id:
        return
    tenant_id = _tenant_of(task)
    if tenant_id is not None:
        _tokens[task_id] = current_tenant_id.set(tenant_id)


def release_tenant(*, task_id: str | None) -> None:
    """Leave the tenant entered by :func:`restore_tenant` (postrun)."""
    token = _tokens.pop(task_id, None) if task_id else None
    if token is None:
        return
    try:
        current_tenant_id.reset(token)
    except ValueError:
        # Token from another context (exotic pool patching): fall back to
        # clearing, so the next task on this worker never inherits a tenant.
        _log.debug("Tenant reset skipped for task_id=%s; clearing", task_id)
        current_tenant_id.set(None)


__all__ = ["TENANT_HEADER", "release_tenant", "restore_tenant", "stamp_tenant"]
