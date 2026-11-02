"""Which tenant a stored file belongs to — and the one way to act as the platform.

``StoredFile`` is ``MultiTenantMixin`` (#383): request code reads, writes and
deletes only the bound tenant's files, and strict mode fails closed with no
tenant bound. Two callers need something else, and both go through here:

* **Upload** must know the owning tenant *before* the row exists, because the
  storage key is prefixed with it and the bytes are written to the backend
  before the row is flushed. :func:`owning_tenant` answers that the same way
  the flush guard will, so a strict install with no tenant fails before any
  object is written rather than after.
* **Platform-owned files** — today, branding's logo and favicon — belong to no
  tenant and must stay readable from anonymous requests, where no tenant is
  bound at all. They are stamped :data:`PLATFORM_TENANT_ID` and read under
  :func:`platform_scope`, restricted to that owner. The id is reserved in
  ``simple_module_db`` — ``is_valid_tenant_id`` refuses it — so no request,
  job or tenant can ever be bound to it, and it is distinct from
  ``DEFAULT_TENANT_ID``, which owns a single-tenant install's ordinary rows.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from simple_module_db import PLATFORM_TENANT_ID, all_tenants, current_tenant_id
from simple_module_db.query_filter import fallback_tenant_id, is_strict
from simple_module_db.tenancy import missing_tenant_error
from sqlalchemy.ext.asyncio import AsyncSession


def owning_tenant(db: AsyncSession, *, platform: bool = False) -> str:
    """The tenant a new upload is stamped with, decided before the bytes move.

    Bound tenant if there is one; ``PLATFORM_TENANT_ID`` for a platform upload;
    on a non-strict install with nothing bound, the install's fallback
    (``default_tenant`` or ``DEFAULT_TENANT_ID``) — the flush guard's own
    choice. Strict with nothing bound raises ``MissingTenantError``.
    """
    if platform:
        return PLATFORM_TENANT_ID
    bound = current_tenant_id.get()
    if bound:
        return bound
    if is_strict(db.sync_session):
        raise missing_tenant_error("StoredFile", "INSERT")
    return fallback_tenant_id(db.sync_session)


@asynccontextmanager
async def platform_scope(db: AsyncSession, platform: bool) -> AsyncGenerator[None]:
    """``all_tenants()`` for platform-file access, a no-op otherwise.

    Callers pair it with a ``tenant_id == PLATFORM_TENANT_ID`` condition, so
    the bypass widens *which context* may read a platform file without letting
    a platform caller reach any tenant's rows.

    The bypass covers the session's whole flush, not one statement, so it must
    never carry the caller's unrelated pending writes along: those are flushed
    first, under the normal guard (stamped with, and checked against, the bound
    tenant), and autoflush is off inside — only what the block itself adds or
    changes is flushed with isolation lifted.
    """
    if not platform:
        yield
        return
    await db.flush()
    with db.no_autoflush, all_tenants():
        yield


__all__ = ["PLATFORM_TENANT_ID", "owning_tenant", "platform_scope"]
