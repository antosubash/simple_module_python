"""Tenant context helpers and the fail-closed isolation policy.

``current_tenant_id`` (set per request by ``TenantMiddleware``) scopes every
query on a :class:`~simple_module_db.mixins.MultiTenantMixin` model. What
happens when it is *unset* is the dangerous case, and depends on
``DatabaseState.tenant_strict``:

* **not strict** (single-tenant installs, the historical default): no filter
  is applied — the query sees every tenant's rows.
* **strict** (enabled whenever the host runs with ``multi_tenant``): the query
  raises :class:`TenantIsolationError` instead. A request, background job or
  CLI command that forgot to establish a tenant fails loudly rather than
  reading across tenants.

Code that legitimately spans tenants (platform admin screens, maintenance
jobs) says so explicitly — per statement with
``stmt.execution_options(all_tenants=True)``, or for a block with
``with all_tenants(): ...``. Code that acts *for* one tenant outside a request
uses ``with tenant_context(tenant_id): ...``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# Set by tenant middleware on each request
current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)

# Set by ``all_tenants()``; lets a block of platform code read across tenants
# while strict isolation is on.
_all_tenants: ContextVar[bool] = ContextVar("sm_all_tenants", default=False)

ALL_TENANTS_OPTION = "all_tenants"
"""Execution option that exempts one statement from tenant scoping."""

TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,49}$")
"""What a tenant id may look like: fits ``MultiTenantMixin.tenant_id``
(``VARCHAR(50)``) and is a printable identifier. Anything taken from a request
(a header, a path) must pass this before it is bound."""


def is_valid_tenant_id(value: object) -> bool:
    return isinstance(value, str) and TENANT_ID_PATTERN.fullmatch(value) is not None


class TenantIsolationError(Exception):
    """Raised when a multi-tenancy isolation constraint is violated."""


@contextmanager
def tenant_context(tenant_id: str) -> Iterator[None]:
    """Run the block as ``tenant_id`` — for jobs, CLI commands and tests."""
    if not is_valid_tenant_id(tenant_id):
        raise ValueError(f"tenant_context() needs a valid tenant id, got {tenant_id!r}")
    token = current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        current_tenant_id.reset(token)


@contextmanager
def all_tenants() -> Iterator[None]:
    """Run the block unscoped: reads see every tenant, strict mode is waived.

    Also clears any active tenant, so a platform job started from inside a
    tenant's request does not silently stay scoped to it. Use sparingly —
    every call site is a place where one tenant can see another's data.
    """
    tenant_token = current_tenant_id.set(None)
    bypass_token = _all_tenants.set(True)
    try:
        yield
    finally:
        _all_tenants.reset(bypass_token)
        current_tenant_id.reset(tenant_token)


def is_all_tenants() -> bool:
    """True inside an ``all_tenants()`` block."""
    return _all_tenants.get()


def missing_tenant_error(entity: str, operation: str) -> TenantIsolationError:
    return TenantIsolationError(
        f"{operation} on tenant-scoped '{entity}' without a tenant context. "
        "Run it inside a request that resolved a tenant, `tenant_context(id)`, "
        "or — for deliberate cross-tenant access — `all_tenants()` / "
        "`execution_options(all_tenants=True)`."
    )


__all__ = [
    "ALL_TENANTS_OPTION",
    "TENANT_ID_PATTERN",
    "TenantIsolationError",
    "all_tenants",
    "current_tenant_id",
    "is_all_tenants",
    "is_valid_tenant_id",
    "missing_tenant_error",
    "tenant_context",
]
