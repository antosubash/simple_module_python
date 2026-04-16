"""SQLModel tables for the Products module."""

from __future__ import annotations

from decimal import Decimal

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own `products` schema; on SQLite
# all modules share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base("products")


class Product(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """A product in the catalog."""

    __tablename__ = "products_product"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal = Field(max_digits=10, decimal_places=2)
    # A plain B-tree over a 2-value boolean is rarely preferred by the planner
    # and costs writes on every insert/update. The listing query filters on
    # ``is_deleted`` (indexed) first, so leaving this un-indexed is faster.
    is_active: bool = Field(default=True)

    __table_args__ = (Index("ix_products_product_is_deleted", "is_deleted"),)
