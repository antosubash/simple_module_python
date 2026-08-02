"""SQLModel tables for the Catalog module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

# All modules share the host's single schema, so __tablename__ is
# prefixed with the module name to avoid collisions.
Base = create_module_base("catalog")


class Catalog(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A catalog entity."""

    __tablename__ = "catalog_catalog"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)
