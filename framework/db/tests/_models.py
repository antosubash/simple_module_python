"""Test-only SQLModel tables used across the database test suite.

Kept in a dedicated module so that ``from conftest import`` is not required at
module level in individual test files (which is fragile when multiple test
directories with their own ``conftest.py`` files are collected in the same
pytest run).
"""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from sqlmodel import Field

_TenantBase = create_module_base("mt_test")


class _TenantItem(_TenantBase, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "mt_test_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class _TenantSoftItem(_TenantBase, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """Combines multi-tenant and soft-delete mixins to test filter composition."""

    __tablename__ = "mt_test_soft_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


_TxnBase = create_module_base("txn_test")


class _TxnThing(_TxnBase, table=True):  # ty: ignore[unsupported-base]
    """Plain table for exercising when the request's unit of work commits."""

    __tablename__ = "txn_test_thing"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
