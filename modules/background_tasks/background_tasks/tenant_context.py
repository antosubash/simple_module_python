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
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from simple_module_db import TenantIsolationError, current_tenant_id, is_valid_tenant_id
from simple_module_db.listeners import current_user_id

from background_tasks.constants import OWNER_ID_MAX_LENGTH

TENANT_HEADER = "sm_tenant_id"
OWNER_HEADER = "sm_owner_id"

_log = logging.getLogger(__name__)
_tokens: dict[str, Token[str | None]] = {}
_owner_tokens: dict[str, Token[str | None]] = {}
# The owner of the task body running on this context, so tasks it enqueues
# carry the same owner. Kept apart from ``current_user_id`` on purpose: that
# one also stamps ``created_by`` on audited rows.
_task_owner: ContextVar[str | None] = ContextVar("sm_task_owner", default=None)
# Single-tenant hosts (``default_tenant``): tasks with no tenant on the message
# — beat jobs, tasks enqueued outside a request — run as that tenant.
_default_tenant: str | None = None


def set_default_tenant(tenant_id: str | None) -> None:
    global _default_tenant
    _default_tenant = tenant_id or None


def default_tenant() -> str | None:
    """The tenant platform work runs as on a single-tenant host, else ``None``."""
    return _default_tenant


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


def stamp_owner(headers: dict[str, Any] | None) -> None:
    """Record the user whose request enqueues this message (publish side).

    A task that enqueues a task has no ``current_user_id`` in its worker, so
    :func:`restore_tenant` binds the incoming message's owner for the body and
    this stamps it onward; :func:`publish_as_owner` does the same for a retry,
    which must keep the original owner rather than adopt the operator. Failing
    both, the bound user is the owner. A header already on the message is
    ignored when a user is bound (request code must not name another owner).
    """
    if headers is None:
        return
    user_id = _task_owner.get()
    if user_id is None:
        user_id = current_user_id.get()
    if user_id:
        headers[OWNER_HEADER] = str(user_id)[:OWNER_ID_MAX_LENGTH]


@contextmanager
def publish_as_owner(owner_user_id: str | None) -> Generator[None]:
    """Publish tasks as *owner_user_id* (``None``: no owner), whoever is bound."""
    token = _task_owner.set(owner_user_id or "")
    try:
        yield
    finally:
        _task_owner.reset(token)


def published_owner(headers: dict[str, Any] | None) -> str | None:
    """The owner an outgoing message carries (call after :func:`stamp_owner`)."""
    value = (headers or {}).get(OWNER_HEADER)
    return str(value)[:OWNER_ID_MAX_LENGTH] if value else None


def published_tenant(headers: dict[str, Any] | None) -> str | None:
    """The tenant an outgoing message is for: its header, else the publisher's.

    Call after :func:`stamp_tenant`. The header may also have been set by
    platform code naming a tenant while none is bound.
    """
    return (headers or {}).get(TENANT_HEADER) or current_tenant_id.get()


def _tenant_of(task: Any) -> str | None:
    return _tenant_of_request(getattr(task, "request", None))


def header_of_request(request: Any, name: str) -> Any:
    """A message header off a running task's request (``Request`` or publish-side object)."""
    value = getattr(request, name, None)
    # A worker ``Request`` (revoked signal) keeps headers in a dict instead.
    for attr in ("headers", "request_dict"):
        if value is None and isinstance(getattr(request, attr, None), dict):
            value = getattr(request, attr).get(name)
    return value


def message_owner(*, task: Any = None, request: Any = None) -> str | None:
    """The owner named on a running task's message header, if any."""
    request = request if request is not None else getattr(task, "request", None)
    if request is None:
        return None
    value = header_of_request(request, OWNER_HEADER)
    return str(value)[:OWNER_ID_MAX_LENGTH] if value else None


def _tenant_of_request(request: Any) -> str | None:
    if request is None:
        return None
    value = header_of_request(request, TENANT_HEADER)
    if not value:
        return None
    if not is_valid_tenant_id(value):
        # Never run a task body as a malformed tenant; it runs unscoped and,
        # under strict mode, fails closed on its first tenant-scoped query.
        _log.warning("Ignoring invalid tenant id on task message: %r", str(value)[:80])
        return None
    return str(value)


def message_tenant(*, task: Any = None, request: Any = None) -> str | None:
    """The tenant named on a running task's message header, if any.

    Signal handlers stamp it onto the ``TaskExecution`` row: the publish signal
    may never have written the row (it fires in the publisher's process, which
    can have a different DB, or none bound), so the worker-side upsert must
    carry the tenant itself. The configured default tenant is deliberately not
    returned — a platform message stays a platform row.
    """
    return _tenant_of_request(request) if request is not None else _tenant_of(task)


def restore_tenant(*, task_id: str | None, task: Any) -> None:
    """Enter the message's tenant for the task body (prerun)."""
    if not task_id:
        return
    owner = message_owner(task=task)
    if owner is not None:
        _owner_tokens[task_id] = _task_owner.set(owner)
    tenant_id = _tenant_of(task) or _default_tenant
    if tenant_id is not None:
        _tokens[task_id] = current_tenant_id.set(tenant_id)


def release_tenant(*, task_id: str | None) -> None:
    """Leave the tenant entered by :func:`restore_tenant` (postrun)."""
    owner_token = _owner_tokens.pop(task_id, None) if task_id else None
    if owner_token is not None:
        try:
            _task_owner.reset(owner_token)
        except ValueError:
            _task_owner.set(None)
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


__all__ = [
    "OWNER_HEADER",
    "TENANT_HEADER",
    "default_tenant",
    "header_of_request",
    "message_owner",
    "message_tenant",
    "publish_as_owner",
    "published_owner",
    "published_tenant",
    "release_tenant",
    "restore_tenant",
    "set_default_tenant",
    "stamp_owner",
    "stamp_tenant",
]
