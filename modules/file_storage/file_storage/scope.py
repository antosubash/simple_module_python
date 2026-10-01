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
  :func:`platform_scope`, restricted to that owner. Tenant ids minted by the
  ``tenants`` module are uuid hex, so this value cannot name a real tenant.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext

from simple_module_db import DEFAULT_TENANT_ID, all_tenants, current_tenant_id
from simple_module_db.query_filter import is_strict
from simple_module_db.tenancy import missing_tenant_error
from sqlalchemy.ext.asyncio import AsyncSession

PLATFORM_TENANT_ID: str = DEFAULT_TENANT_ID
"""Owner of platform files. The same value a single-tenant install stamps on
every unbound insert, and the one the adoption migration back-filled — so the
branding images uploaded before this change are platform files already."""


def owning_tenant(db: AsyncSession, *, platform: bool = False) -> str:
    """The tenant a new upload is stamped with, decided before the bytes move.

    Bound tenant if there is one; ``PLATFORM_TENANT_ID`` for a platform upload
    or on a non-strict install with nothing bound (matching the flush guard's
    own fallback). Strict with nothing bound raises ``MissingTenantError``.
    """
    if platform:
        return PLATFORM_TENANT_ID
    bound = current_tenant_id.get()
    if bound:
        return bound
    if is_strict(db.sync_session):
        raise missing_tenant_error("StoredFile", "INSERT")
    return DEFAULT_TENANT_ID


@contextmanager
def platform_scope(platform: bool) -> Iterator[None]:
    """``all_tenants()`` for platform-file access, a no-op otherwise.

    Callers pair it with a ``tenant_id == PLATFORM_TENANT_ID`` condition, so
    the bypass widens *which context* may read a platform file without letting
    a platform caller reach any tenant's rows.
    """
    with all_tenants() if platform else nullcontext():
        yield


__all__ = ["PLATFORM_TENANT_ID", "owning_tenant", "platform_scope"]
