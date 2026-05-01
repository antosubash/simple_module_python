"""Entity mixins for cross-cutting concerns (audit, soft delete, tenancy, versioning).

We use ``sa_type`` + ``sa_column_kwargs`` (not ``sa_column=Column(...)``) so
SQLModel constructs a fresh ``Column`` per concrete subclass; sharing a single
``Column`` across mixin subclasses raises
``ArgumentError: Column already assigned to Table``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC ``now`` for the Python-side default of ``created_at``."""
    return datetime.now(UTC)


class AuditMixin(SQLModel):
    """Adds created_at, updated_at, created_by, updated_by fields.

    ``created_at`` is populated both Python-side (``default_factory``) and
    server-side (``server_default``) so freshly-instantiated instances can
    be serialized before flush — without the Python default, accessing
    ``obj.created_at`` raised ``AttributeError`` until the row hit the DB.
    ``updated_at`` is populated by the audit listener in
    :mod:`simple_module_db.listeners`.
    """

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": func.now()},
    )
    created_by: str | None = Field(default=None, max_length=255)
    updated_by: str | None = Field(default=None, max_length=255)


class SoftDeleteMixin(SQLModel):
    """Marks records as deleted instead of removing them.

    Query filters installed by :func:`register_listeners` exclude
    ``is_deleted=True`` rows by default. Use
    ``stmt.execution_options(include_deleted=True)`` to bypass.
    """

    is_deleted: bool = Field(default=False)
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    deleted_by: str | None = Field(default=None, max_length=255)


class MultiTenantMixin(SQLModel):
    """Adds a tenant_id column for data isolation in multi-tenant apps.

    The Python-side type is optional so callers can construct an instance
    inside a request scope without explicitly threading the tenant through —
    the ``_before_flush_listener`` in :mod:`simple_module_db.listeners`
    populates it from the ``current_tenant_id`` contextvar before the row
    reaches the DB. The column itself is non-nullable, so a row inserted
    outside any tenant context fails loudly at the DB rather than silently
    leaking across tenants.
    """

    tenant_id: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        sa_column_kwargs={"nullable": False},
    )


class VersionedMixin(SQLModel):
    """Optimistic concurrency via an auto-incrementing version field."""

    version: int = Field(default=1)
