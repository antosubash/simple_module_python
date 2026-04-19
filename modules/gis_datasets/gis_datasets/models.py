"""SQLModel tables for the GisDatasets module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own `gis_datasets` schema; on SQLite
# all modules share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base("gis_datasets")


class Dataset(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """A geospatial dataset uploaded into the catalog."""

    __tablename__ = "gis_datasets_dataset"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    slug: str = Field(max_length=200, unique=True, index=True)
    kind: str = Field(max_length=32, index=True)
    description: str | None = Field(default=None, max_length=2000)

    original_filename: str = Field(max_length=255)
    mime_type: str | None = Field(default=None, max_length=127)
    size_bytes: int = Field(default=0)
    storage_key: str = Field(max_length=512)

    crs: str | None = Field(default=None, max_length=64)
    bbox_min_x: float | None = Field(default=None)
    bbox_min_y: float | None = Field(default=None)
    bbox_max_x: float | None = Field(default=None)
    bbox_max_y: float | None = Field(default=None)
    feature_count: int | None = Field(default=None)
    band_count: int | None = Field(default=None)
    extraction_status: str = Field(default="manual", max_length=16)

    __table_args__ = (Index("ix_gis_datasets_dataset_is_deleted", "is_deleted"),)
