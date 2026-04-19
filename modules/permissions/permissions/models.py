"""SQLModel tables for the Permissions module.

The *set* of available permission keys lives in the in-memory
:class:`simple_module_core.permissions.PermissionRegistry` — each module
declares them via :meth:`ModuleBase.register_permissions`, and they are
auto-discovered at boot. What needs persistence is the mutable mapping
of those keys onto the principals that receive them:

* :class:`RolePermission` — keys granted to every user in a named role.
* :class:`UserPermission` — keys granted directly to a single user, on
  top of (or independent of) any role they happen to hold.

Both junction rows are keyed on plain strings rather than FKs into the
``users`` schema — per-module :class:`MetaData` cannot express a
cross-module foreign key, and this keeps the permissions module
independent of ``users``' table layout.
"""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations.

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID, now_utc
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import DateTime, Index
from sqlmodel import Field

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own `permissions` schema; on SQLite
# all modules share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base("permissions")


class RolePermission(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Assignment of a registered permission key to a role."""

    __tablename__ = "permissions_role_permission"

    role_name: str = Field(max_length=64, primary_key=True)
    permission_key: str = Field(max_length=128, primary_key=True)
    assigned_at: datetime = Field(
        default_factory=now_utc,
        sa_type=DateTime(timezone=True),
    )
    assigned_by: str | None = Field(default=None, max_length=255)


class UserPermission(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Direct assignment of a registered permission key to a single user."""

    __tablename__ = "permissions_user_permission"

    user_id: uuid.UUID = Field(sa_type=GUID, primary_key=True)
    permission_key: str = Field(max_length=128, primary_key=True)
    assigned_at: datetime = Field(
        default_factory=now_utc,
        sa_type=DateTime(timezone=True),
    )
    assigned_by: str | None = Field(default=None, max_length=255)

    # Reverse lookups ("who has this permission directly?") are rare but cheap.
    __table_args__ = (Index("ix_permissions_user_permission_key", "permission_key"),)
