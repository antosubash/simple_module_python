"""SQLAlchemy models for the Products module."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from simple_module_db.provider import DatabaseProvider, detect_provider

# Each module gets its own schema: "products" on PostgreSQL, "products_" prefix on SQLite
# Provider is detected at import time; for runtime flexibility, call create_module_base
# again with the actual provider in on_startup if needed.
Base = create_module_base("products", provider=DatabaseProvider.SQLITE)


class Product(Base, AuditMixin):
    """A product in the catalog."""

    __tablename__ = "products_product"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True)
