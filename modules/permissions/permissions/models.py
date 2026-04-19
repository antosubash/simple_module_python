"""SQLModel tables for the Permissions module.

The *set* of available permission keys lives in the in-memory
:class:`simple_module_core.permissions.PermissionRegistry` — each module
declares them via :meth:`ModuleBase.register_permissions`. What needs
persistence is the mutable role-to-permission mapping an admin edits at
runtime, so this module owns only that junction table.

The junction keys on :attr:`users.models.Role.name` (which is uniquely
indexed) rather than ``role_id``. That keeps the schema independent of the
``users`` module's tables — per-module :class:`MetaData` cannot express a
cross-module foreign key — and matches how the in-memory
:class:`PermissionRegistry` already identifies roles (by name).
"""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations.

from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import now_utc
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import DateTime
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
