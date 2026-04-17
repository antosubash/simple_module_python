"""Entity mixins for cross-cutting concerns (audit, soft delete, tenancy, versioning).

We use ``sa_type`` + ``sa_column_kwargs`` (not ``sa_column=Column(...)``) so
SQLModel constructs a fresh ``Column`` per concrete subclass; sharing a single
``Column`` across mixin subclasses raises
``ArgumentError: Column already assigned to Table``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class AuditMixin(SQLModel):
    """Adds created_at, updated_at, created_by, updated_by fields.

    ``created_at`` gets a server-side default; ``updated_at`` is populated by
    the audit listener in :mod:`simple_module_db.listeners`.
    """

    created_at: datetime = Field(
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
    """Adds a tenant_id column for data isolation in multi-tenant apps."""

    tenant_id: str = Field(max_length=50, index=True)


class VersionedMixin(SQLModel):
    """Optimistic concurrency via an auto-incrementing version field."""

    version: int = Field(default=1)
