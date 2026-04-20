"""SQLModel DTOs for the Datasets module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from datasets import constants

DatasetKind = Literal[
    "vector_geojson",
    "vector_shapefile",
    "vector_kml",
    "raster_geotiff",
    "tabular_csv",
    "other",
]

# Duplicated from ``constants.ALL_KINDS`` because ``typing.Literal`` demands
# string literals at type-evaluation time — a tuple reference won't satisfy
# it. The runtime check against ``constants.ALL_KINDS`` is the one that
# matters; this Literal only narrows the ``DatasetUpdate.kind`` type.
KIND_VALUES: tuple[str, ...] = constants.ALL_KINDS


class DatasetOut(SQLModel):
    """Dataset metadata returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    kind: str
    description: str | None = None
    original_filename: str
    mime_type: str | None = None
    size_bytes: int
    crs: str | None = None
    bbox_min_x: float | None = None
    bbox_min_y: float | None = None
    bbox_max_x: float | None = None
    bbox_max_y: float | None = None
    feature_count: int | None = None
    band_count: int | None = None
    extraction_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetUpdate(SQLModel):
    """Patchable metadata. Files are immutable after upload — re-upload to replace."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    kind: DatasetKind | None = None
    crs: str | None = Field(default=None, max_length=64)
    bbox_min_x: float | None = None
    bbox_min_y: float | None = None
    bbox_max_x: float | None = None
    bbox_max_y: float | None = None
