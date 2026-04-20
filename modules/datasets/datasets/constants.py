"""Stable identifiers for the datasets module.

Every string that identifies a permission, role, page, module dependency,
event, route, or config key lives here. Everything else in the module
imports from this file, so ``rg`` can prove the module has no scattered
magic strings.
"""

from __future__ import annotations

from typing import Final

# ── Module identity ──────────────────────────────────────────────────
MODULE_NAME: Final = "datasets"
MODULE_PASCAL: Final = "Datasets"
MODULE_DISPLAY_NAME: Final = "Datasets"

# ── Configuration ────────────────────────────────────────────────────
ENV_PREFIX: Final = "SM_DATASETS_"

# ── Routing ──────────────────────────────────────────────────────────
ROUTE_PREFIX_API: Final = "/api/datasets"
ROUTE_PREFIX_VIEW: Final = "/datasets"

# REST sub-paths (joined to ROUTE_PREFIX_API by the router)
PATH_DOWNLOAD: Final = "/{dataset_id}/download"
PATH_DATASET: Final = "/{dataset_id}"

# View routes (relative to ROUTE_PREFIX_VIEW, used in redirects)
REDIRECT_BROWSE: Final = "/datasets/"

# ── Module dependencies (for ModuleMeta.depends_on) ──────────────────
MODULE_FILE_STORAGE: Final = "FileStorage"
MODULE_BACKGROUND_TASKS: Final = "BackgroundTasks"

# ── i18n ─────────────────────────────────────────────────────────────
LOCALE_NAMESPACE: Final = MODULE_NAME

# ── Inertia page identifiers ─────────────────────────────────────────
PAGE_BROWSE: Final = "Datasets/Browse"
PAGE_CREATE: Final = "Datasets/Create"
PAGE_EDIT: Final = "Datasets/Edit"
PAGE_SHOW: Final = "Datasets/Show"

# ── Permissions ──────────────────────────────────────────────────────
PERM_DATASETS_VIEW: Final = "datasets.view"
PERM_DATASETS_UPLOAD: Final = "datasets.upload"
PERM_DATASETS_EDIT: Final = "datasets.edit"
PERM_DATASETS_DELETE: Final = "datasets.delete"

PERMISSION_GROUP: Final = "Datasets"
ALL_PERMISSIONS: Final = (
    PERM_DATASETS_VIEW,
    PERM_DATASETS_UPLOAD,
    PERM_DATASETS_EDIT,
    PERM_DATASETS_DELETE,
)

# ── Menu ─────────────────────────────────────────────────────────────
MENU_LABEL: Final = "Datasets"
MENU_ICON: Final = "layers"
MENU_ORDER: Final = 40

# ── Celery tasks ─────────────────────────────────────────────────────
TASK_EXTRACT_METADATA: Final = "datasets.extract_metadata"

# ── Health check ─────────────────────────────────────────────────────
HEALTH_CHECK_STORAGE: Final = "datasets.storage"

# ── Storage ──────────────────────────────────────────────────────────
STORAGE_KEY_PREFIX: Final = "datasets/"

# ── Database ─────────────────────────────────────────────────────────
SCHEMA_NAME: Final = "datasets"
TABLE_DATASET: Final = "datasets_dataset"

# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_MAX_UPLOAD_MB: Final = 256
DEFAULT_UPLOAD_CHUNK_SIZE: Final = 1024 * 1024  # 1 MB
DEFAULT_PRESIGN_TTL_SECONDS: Final = 300  # 5 minutes
DEFAULT_FALLBACK_FILENAME: Final = "upload.bin"
DEFAULT_MIME_TYPE: Final = "application/octet-stream"
DEFAULT_GEOJSON_CRS: Final = "EPSG:4326"


class DatasetKind:
    """Built-in dataset kinds.

    The ``kind`` column is a free-form string so new providers can register
    their own labels, but these are the ones the shipped extractors and
    the UI know about.
    """

    VECTOR_GEOJSON: Final = "vector_geojson"
    VECTOR_SHAPEFILE: Final = "vector_shapefile"
    VECTOR_KML: Final = "vector_kml"
    RASTER_GEOTIFF: Final = "raster_geotiff"
    TABULAR_CSV: Final = "tabular_csv"
    OTHER: Final = "other"


ALL_KINDS: Final = (
    DatasetKind.VECTOR_GEOJSON,
    DatasetKind.VECTOR_SHAPEFILE,
    DatasetKind.VECTOR_KML,
    DatasetKind.RASTER_GEOTIFF,
    DatasetKind.TABULAR_CSV,
    DatasetKind.OTHER,
)


class ExtractionStatus:
    """Values stored in ``Dataset.extraction_status``.

    ``pending`` is set by the upload endpoint; ``ok``/``partial``/``failed``
    are set by the Celery worker once extraction completes. ``manual`` is
    the fallback for kinds the extractor doesn't understand; ``not_found``
    is only used as a task-result marker (never stored).
    """

    PENDING: Final = "pending"
    OK: Final = "ok"
    PARTIAL: Final = "partial"
    FAILED: Final = "failed"
    MANUAL: Final = "manual"
    NOT_FOUND: Final = "not_found"
