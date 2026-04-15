"""Test-only SQLAlchemy models used across the database test suite.

Kept in a dedicated module so that ``from conftest import`` is not required at
module level in individual test files (which is fragile when multiple test
directories with their own ``conftest.py`` files are collected in the same
pytest run).
"""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.provider import DatabaseProvider
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

_TenantBase = create_module_base("mt_test", provider=DatabaseProvider.SQLITE)


class _TenantItem(_TenantBase, MultiTenantMixin):  # ty: ignore[unsupported-base]
    __tablename__ = "mt_test_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


class _TenantSoftItem(_TenantBase, MultiTenantMixin, SoftDeleteMixin):  # ty: ignore[unsupported-base]
    """Combines multi-tenant and soft-delete mixins to test filter composition."""

    __tablename__ = "mt_test_soft_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
