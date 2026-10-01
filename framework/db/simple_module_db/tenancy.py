"""Tenant context helpers and the fail-closed isolation policy.

``current_tenant_id`` (set per request by ``TenantMiddleware``) scopes every
query on a :class:`~simple_module_db.mixins.MultiTenantMixin` model. What
happens when it is *unset* is the dangerous case, and depends on
``DatabaseState.tenant_strict``:

* **not strict** (single-tenant installs, the historical default): no filter
  is applied — the query sees every tenant's rows — and an insert is stamped
  with :data:`DEFAULT_TENANT_ID`.
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

import functools
import inspect
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

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


DEFAULT_TENANT_ID = "default"
"""The tenant a row lands in when tenancy is not strict and none is bound.

A single-tenant install (``multi_tenant`` off) has no tenant to bind, but
``MultiTenantMixin.tenant_id`` is NOT NULL, so inserts are stamped with this.
Adoption migrations backfill existing rows with the same value. It is not the
``default_tenant`` host setting: that one *binds* a tenant per request, and
when set it replaces this constant as the fallback
(``DatabaseState.default_tenant_id``). Strict mode never uses either.
"""


def is_valid_tenant_id(value: object) -> bool:
    return isinstance(value, str) and TENANT_ID_PATTERN.fullmatch(value) is not None


class TenantIsolationError(Exception):
    """Raised when a multi-tenancy isolation constraint is violated."""


class MissingTenantError(TenantIsolationError):
    """A tenant-scoped operation ran with no tenant bound (strict mode).

    Distinct from its parent so a request handler can tell "this user has no
    organisation yet" (a user state) from a cross-tenant write (a bug or an
    attack) and answer them differently.
    """


@contextmanager
def tenant_context(tenant_id: str) -> Iterator[None]:
    """Run the block as ``tenant_id`` — for jobs, CLI commands and tests.

    Wins over an enclosing ``all_tenants()``: the natural platform job is
    ``with all_tenants(): for t in tenants: with tenant_context(t): ...``, and
    each iteration must be scoped to ``t``, not left unscoped.
    """
    if not is_valid_tenant_id(tenant_id):
        raise ValueError(f"tenant_context() needs a valid tenant id, got {tenant_id!r}")
    token = current_tenant_id.set(tenant_id)
    bypass_token = _all_tenants.set(False)
    try:
        yield
    finally:
        _all_tenants.reset(bypass_token)
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


def bind_current_tenant[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Wrap ``fn`` so it runs as the tenant bound *now*, whenever it is called.

    For work a module defers past the point where the request's tenant is
    reset (#364) — its own after-response queue, a thread pool, a callback
    registry. ``db.on_commit`` callbacks and FastAPI ``BackgroundTasks`` do
    not need it: both run inside the request's tenant scope already.
    Works for sync and async callables; captures ``all_tenants()`` too.
    """
    tenant_id = current_tenant_id.get()
    bypass = _all_tenants.get()

    def _enter() -> tuple[Any, Any]:
        return current_tenant_id.set(tenant_id), _all_tenants.set(bypass)

    def _exit(tokens: tuple[Any, Any]) -> None:
        _all_tenants.reset(tokens[1])
        current_tenant_id.reset(tokens[0])

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def run_async(*args: P.args, **kwargs: P.kwargs) -> Any:
            tokens = _enter()
            try:
                return await fn(*args, **kwargs)
            finally:
                _exit(tokens)

        return run_async  # ty: ignore[invalid-return-type]

    @functools.wraps(fn)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        tokens = _enter()
        try:
            return fn(*args, **kwargs)
        finally:
            _exit(tokens)

    return run


def is_all_tenants() -> bool:
    """True inside an ``all_tenants()`` block."""
    return _all_tenants.get()


def missing_tenant_error(entity: str, operation: str) -> MissingTenantError:
    return MissingTenantError(
        f"{operation} on tenant-scoped '{entity}' without a tenant context. "
        "Run it inside a request that resolved a tenant, `tenant_context(id)`, "
        "or — for deliberate cross-tenant access — `all_tenants()` / "
        "`execution_options(all_tenants=True)`."
    )


__all__ = [
    "ALL_TENANTS_OPTION",
    "DEFAULT_TENANT_ID",
    "TENANT_ID_PATTERN",
    "MissingTenantError",
    "TenantIsolationError",
    "all_tenants",
    "bind_current_tenant",
    "current_tenant_id",
    "is_all_tenants",
    "is_valid_tenant_id",
    "missing_tenant_error",
    "tenant_context",
]
