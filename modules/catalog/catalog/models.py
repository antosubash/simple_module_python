"""SQLModel tables for the Catalog module."""

from __future__ import annotations

import uuid

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

from catalog.constants import (
    DESCRIPTION_MAX_LENGTH,
    MODULE_PACKAGE,
    NAME_MAX_LENGTH,
    SKU_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    STATUS_DRAFT,
    STATUS_MAX_LENGTH,
    TABLE_CATEGORY,
    TABLE_PRODUCT,
)

# All modules share the host's single schema, so __tablename__ is
# prefixed with the module name to avoid collisions.
Base = create_module_base(MODULE_PACKAGE)


class Category(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A product grouping."""

    __tablename__ = TABLE_CATEGORY

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    slug: str = Field(max_length=SLUG_MAX_LENGTH, unique=True, index=True)


class Product(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """A catalog product."""

    # The composite (status, created_at) matches the default list ordering under
    # a status filter, so the common browse query is served by one index rather
    # than a filter scan followed by a sort.
    __table_args__ = (
        Index("ix_catalog_product_name", "name"),
        Index("ix_catalog_product_status_created_at", "status", "created_at"),
        Index("ix_catalog_product_category_id", "category_id"),
    )
    __tablename__ = TABLE_PRODUCT

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sku: str = Field(max_length=SKU_MAX_LENGTH, unique=True, index=True)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    status: str = Field(default=STATUS_DRAFT, max_length=STATUS_MAX_LENGTH)
    price_cents: int = Field(default=0)
    category_id: uuid.UUID = Field(foreign_key=f"{TABLE_CATEGORY}.id")
