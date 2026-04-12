"""Entity mixins for cross-cutting concerns (audit, soft delete, tenancy, versioning)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    """Adds created_at, updated_at, created_by, updated_by fields.

    Auto-populated by the audit event listener in ``listeners.py``.
    """

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(onupdate=func.now(), default=None)
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)
    updated_by: Mapped[str | None] = mapped_column(String(255), default=None)


class SoftDeleteMixin:
    """Marks records as deleted instead of removing them.

    Query filters should exclude ``is_deleted=True`` by default.
    """

    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    deleted_by: Mapped[str | None] = mapped_column(String(255), default=None)


class MultiTenantMixin:
    """Adds a tenant_id column for data isolation in multi-tenant apps."""

    tenant_id: Mapped[str] = mapped_column(String(50), index=True)


class VersionedMixin:
    """Optimistic concurrency via an auto-incrementing version field."""

    version: Mapped[int] = mapped_column(default=1)
