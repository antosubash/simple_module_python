"""Test-only SQLModel tables for the audit test suite.

Kept in a dedicated module so the model definitions don't push
``test_audit.py`` over the 300-line file size cap.
"""

from __future__ import annotations

from typing import ClassVar

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlmodel import Field

AuditBase = create_module_base("test_audit")


class AuditTestItem(AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Standard audited entity for testing."""

    __tablename__ = "test_audit_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    value: int = Field(default=0)


class ExcludedModel(AuditBase, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Model that opts out of auditing entirely."""

    __tablename__ = "test_audit_excluded"
    __audit_exclude__ = True
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class PartialExcludeModel(AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Model with specific fields excluded from audit tracking."""

    __tablename__ = "test_audit_partial"
    __audit_exclude_fields__: ClassVar[set[str]] = {"password_hash"}
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=100)
    password_hash: str = Field(max_length=255, default="")


class SoftDeleteItem(AuditBase, AuditMixin, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Audited entity with soft-delete support for testing."""

    __tablename__ = "test_audit_soft_delete_item"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=100)


class IntPKItem(AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Entity with a DB-assigned integer primary key (BUG-002 regression case)."""

    __tablename__ = "test_audit_int_pk_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
