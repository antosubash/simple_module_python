"""Best-effort metadata extraction for uploaded datasets.

GeoJSON is handled with ``shapely`` (a standard geospatial dependency).
Optional ``fiona`` and ``rasterio`` extras enrich extraction for
shapefiles, KML, and rasters when available. Every extractor degrades
to ``ExtractionStatus.MANUAL`` so the catalog never blocks an upload
because a parser is missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape

from datasets import constants
from datasets.constants import DatasetKind, ExtractionStatus


@dataclass
class ExtractedMeta:
    crs: str | None = None
    bbox_min_x: float | None = None
    bbox_min_y: float | None = None
    bbox_max_x: float | None = None
    bbox_max_y: float | None = None
    feature_count: int | None = None
    band_count: int | None = None
    status: str = ExtractionStatus.MANUAL


_EXTENSION_TO_KIND: dict[str, str] = {
    ".geojson": DatasetKind.VECTOR_GEOJSON,
    ".json": DatasetKind.VECTOR_GEOJSON,
    ".shp": DatasetKind.VECTOR_SHAPEFILE,
    ".zip": DatasetKind.VECTOR_SHAPEFILE,
    ".kml": DatasetKind.VECTOR_KML,
    ".kmz": DatasetKind.VECTOR_KML,
    ".tif": DatasetKind.RASTER_GEOTIFF,
    ".tiff": DatasetKind.RASTER_GEOTIFF,
    ".csv": DatasetKind.TABULAR_CSV,
}


def kind_for_filename(filename: str) -> str:
    """Map a filename to a coarse kind label.

    The mapping is intentionally cheap — anything we don't recognise becomes
    ``DatasetKind.OTHER`` so the upload still lands and the user can correct
    the kind via the edit form.
    """
    suffix = Path(filename).suffix.lower()
    return _EXTENSION_TO_KIND.get(suffix, DatasetKind.OTHER)


def extract_metadata(path: Path, kind: str) -> ExtractedMeta:
    """Dispatch to a kind-specific extractor.

    Never raises — extraction failures collapse to
    ``ExtractionStatus.FAILED`` so the upload itself succeeds and the user
    can fill the metadata in.
    """
    try:
        if kind == DatasetKind.VECTOR_GEOJSON:
            return _extract_geojson(path)
        if kind == DatasetKind.RASTER_GEOTIFF:
            return _extract_raster(path)
        if kind in {DatasetKind.VECTOR_SHAPEFILE, DatasetKind.VECTOR_KML}:
            return _extract_via_fiona(path)
    except Exception:
        return ExtractedMeta(status=ExtractionStatus.FAILED)
    return ExtractedMeta(status=ExtractionStatus.MANUAL)


def _extract_geojson(path: Path) -> ExtractedMeta:
    with path.open("rb") as fp:
        doc = json.load(fp)

    features: list[dict]
    if isinstance(doc, dict) and doc.get("type") == "FeatureCollection":
        features = [f for f in doc.get("features", []) if isinstance(f, dict)]
    elif isinstance(doc, dict) and doc.get("type") == "Feature":
        features = [doc]
    else:
        features = []

    bbox = doc.get("bbox") if isinstance(doc, dict) else None
    if not bbox:
        bounds = [
            shape(f["geometry"]).bounds for f in features if isinstance(f.get("geometry"), dict)
        ]
        if bounds:
            bbox = (
                min(b[0] for b in bounds),
                min(b[1] for b in bounds),
                max(b[2] for b in bounds),
                max(b[3] for b in bounds),
            )

    if not bbox:
        return ExtractedMeta(
            crs=constants.DEFAULT_GEOJSON_CRS,
            feature_count=len(features),
            status=ExtractionStatus.PARTIAL,
        )
    return ExtractedMeta(
        crs=constants.DEFAULT_GEOJSON_CRS,
        bbox_min_x=float(bbox[0]),
        bbox_min_y=float(bbox[1]),
        bbox_max_x=float(bbox[2]),
        bbox_max_y=float(bbox[3]),
        feature_count=len(features),
        status=ExtractionStatus.OK,
    )


def _extract_via_fiona(path: Path) -> ExtractedMeta:
    try:
        import fiona  # type: ignore[import-not-found]  # ty: ignore[unresolved-import]
    except ImportError:
        return ExtractedMeta(status=ExtractionStatus.MANUAL)

    with fiona.open(str(path)) as src:
        bounds = src.bounds
        crs = src.crs.get("init") if hasattr(src.crs, "get") else str(src.crs) if src.crs else None
        return ExtractedMeta(
            crs=crs,
            bbox_min_x=float(bounds[0]),
            bbox_min_y=float(bounds[1]),
            bbox_max_x=float(bounds[2]),
            bbox_max_y=float(bounds[3]),
            feature_count=len(src),
            status=ExtractionStatus.OK,
        )


def _extract_raster(path: Path) -> ExtractedMeta:
    try:
        import rasterio  # type: ignore[import-not-found]  # ty: ignore[unresolved-import]
    except ImportError:
        return ExtractedMeta(status=ExtractionStatus.MANUAL)

    with rasterio.open(str(path)) as src:
        bounds = src.bounds
        return ExtractedMeta(
            crs=str(src.crs) if src.crs else None,
            bbox_min_x=float(bounds.left),
            bbox_min_y=float(bounds.bottom),
            bbox_max_x=float(bounds.right),
            bbox_max_y=float(bounds.top),
            band_count=src.count,
            status=ExtractionStatus.OK,
        )
