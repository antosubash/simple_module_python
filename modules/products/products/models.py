"""SQLAlchemy models for the Products module."""

from __future__ import annotations

from decimal import Decimal

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own `products` schema; on SQLite
# all modules share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base("products")


class Product(Base, AuditMixin, SoftDeleteMixin):  # ty: ignore[unsupported-base]
    """A product in the catalog."""

    __tablename__ = "products_product"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
