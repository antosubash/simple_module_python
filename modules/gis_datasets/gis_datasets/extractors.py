"""Best-effort metadata extraction for uploaded GIS datasets.

The stdlib JSON path covers GeoJSON without any extra dependency. Optional
``fiona`` and ``rasterio`` extras enrich extraction for shapefiles, KML, and
rasters when available. Every extractor degrades to ``status="manual"`` so
the catalog never blocks an upload because a parser is missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractedMeta:
    crs: str | None = None
    bbox_min_x: float | None = None
    bbox_min_y: float | None = None
    bbox_max_x: float | None = None
    bbox_max_y: float | None = None
    feature_count: int | None = None
    band_count: int | None = None
    status: str = "manual"


def kind_for_filename(filename: str) -> str:
    """Map a filename to a coarse kind label.

    The mapping is intentionally cheap — anything we don't recognise becomes
    ``"other"`` so the upload still lands and the user can correct the kind
    via the edit form.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".geojson" or suffix == ".json":
        return "vector_geojson"
    if suffix in {".shp", ".zip"}:
        return "vector_shapefile"
    if suffix in {".kml", ".kmz"}:
        return "vector_kml"
    if suffix in {".tif", ".tiff"}:
        return "raster_geotiff"
    if suffix == ".csv":
        return "tabular_csv"
    return "other"


def extract_metadata(path: Path, kind: str) -> ExtractedMeta:
    """Dispatch to a kind-specific extractor.

    Never raises — extraction failures collapse to ``status="failed"`` so
    the upload itself succeeds and the user can fill the metadata in.
    """
    try:
        if kind == "vector_geojson":
            return _extract_geojson(path)
        if kind == "raster_geotiff":
            return _extract_raster(path)
        if kind in {"vector_shapefile", "vector_kml"}:
            return _extract_via_fiona(path)
    except Exception:
        return ExtractedMeta(status="failed")
    return ExtractedMeta(status="manual")


def _extract_geojson(path: Path) -> ExtractedMeta:
    with path.open("rb") as fp:
        doc = json.load(fp)

    features = _features(doc)
    bbox = doc.get("bbox") if isinstance(doc, dict) else None
    if not bbox:
        bbox = _compute_bbox(features)

    if bbox is None:
        return ExtractedMeta(
            crs="EPSG:4326",
            feature_count=len(features),
            status="partial",
        )
    return ExtractedMeta(
        crs="EPSG:4326",
        bbox_min_x=float(bbox[0]),
        bbox_min_y=float(bbox[1]),
        bbox_max_x=float(bbox[2]),
        bbox_max_y=float(bbox[3]),
        feature_count=len(features),
        status="ok",
    )


def _features(doc: object) -> list[dict]:
    if isinstance(doc, dict):
        if doc.get("type") == "FeatureCollection":
            features = doc.get("features", [])
            return [f for f in features if isinstance(f, dict)]
        if doc.get("type") == "Feature":
            return [doc]
    return []


def _compute_bbox(features: list[dict]) -> tuple[float, float, float, float] | None:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for feature in features:
        geom = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geom, dict):
            continue
        for x, y in _iter_coords(geom):
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if min_x == float("inf"):
        return None
    return min_x, min_y, max_x, max_y


def _iter_coords(geom: dict):
    coords = geom.get("coordinates")
    geom_type = geom.get("type")
    if geom_type == "GeometryCollection":
        for sub in geom.get("geometries", []):
            if isinstance(sub, dict):
                yield from _iter_coords(sub)
        return
    yield from _walk(coords)


def _walk(node: object):
    if (
        isinstance(node, list)
        and len(node) >= 2
        and all(isinstance(v, (int, float)) for v in node[:2])
    ):
        yield float(node[0]), float(node[1])
        return
    if isinstance(node, list):
        for child in node:
            yield from _walk(child)


def _extract_via_fiona(path: Path) -> ExtractedMeta:
    try:
        import fiona  # type: ignore[import-not-found]  # ty: ignore[unresolved-import]
    except ImportError:
        return ExtractedMeta(status="manual")

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
            status="ok",
        )


def _extract_raster(path: Path) -> ExtractedMeta:
    try:
        import rasterio  # type: ignore[import-not-found]  # ty: ignore[unresolved-import]
    except ImportError:
        return ExtractedMeta(status="manual")

    with rasterio.open(str(path)) as src:
        bounds = src.bounds
        return ExtractedMeta(
            crs=str(src.crs) if src.crs else None,
            bbox_min_x=float(bounds.left),
            bbox_min_y=float(bounds.bottom),
            bbox_max_x=float(bounds.right),
            bbox_max_y=float(bounds.top),
            band_count=src.count,
            status="ok",
        )
