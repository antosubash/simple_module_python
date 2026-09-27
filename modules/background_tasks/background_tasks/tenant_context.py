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

from simple_module_db import current_tenant_id

TENANT_HEADER = "sm_tenant_id"

_log = logging.getLogger(__name__)
_tokens: dict[str, Token[str | None]] = {}


def stamp_tenant(headers: dict[str, Any] | None) -> None:
    """Record the current tenant on an outgoing message (publish side).

    An explicit value already present — a caller passing
    ``headers={"sm_tenant_id": ...}`` to ``send_task`` — is kept.
    """
    if headers is None or headers.get(TENANT_HEADER):
        return
    tenant_id = current_tenant_id.get()
    if tenant_id is not None:
        headers[TENANT_HEADER] = tenant_id


def _tenant_of(task: Any) -> str | None:
    request = getattr(task, "request", None)
    if request is None:
        return None
    value = getattr(request, TENANT_HEADER, None)
    if value is None and isinstance(getattr(request, "headers", None), dict):
        value = request.headers.get(TENANT_HEADER)
    return str(value) if value else None


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
