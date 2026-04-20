"""SQLModel tables for the Datasets module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

from datasets import constants

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own schema; on SQLite all modules
# share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base(constants.SCHEMA_NAME)


class Dataset(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """A dataset uploaded into the catalog.

    ``kind`` identifies the content type (vector GeoJSON, shapefile,
    raster GeoTIFF, tabular CSV, ...) — see
    :class:`datasets.constants.DatasetKind`. Geospatial fields (``crs``,
    ``bbox_*``) stay null for non-geospatial kinds.
    """

    __tablename__ = constants.TABLE_DATASET

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
    extraction_status: str = Field(default=constants.ExtractionStatus.MANUAL, max_length=16)

    __table_args__ = (Index("ix_datasets_dataset_is_deleted", "is_deleted"),)
