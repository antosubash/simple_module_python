"""Datasets contracts — public interface for other modules.

Downstream modules should import from here, not from
``datasets.models`` or ``datasets.storage`` (those are internal).
The SM009 diagnostic enforces framework→plugin purity; this package
is the supported surface for plugin→plugin coupling::

    from datasets.contracts import (
        DatasetOut,            # DTO returned by service lookups
        DatasetFile,           # handle for on-disk file access
        IDatasetService,       # Protocol for type hints
        DatasetUploaded,       # event subscribers listen for
        download_url,          # URL helper for UIs
    )

For the FastAPI dependency, prefer
``from datasets.deps import DatasetServiceDep``.
"""

from datasets.contracts.events import DatasetDeleted, DatasetUploaded
from datasets.contracts.files import DatasetFile
from datasets.contracts.schemas import (
    KIND_VALUES,
    DatasetKind,
    DatasetOut,
    DatasetUpdate,
)
from datasets.contracts.service import IDatasetService
from datasets.contracts.urls import (
    API_PREFIX,
    VIEW_PREFIX,
    detail_url,
    download_url,
    show_url,
)

__all__ = [
    "API_PREFIX",
    "KIND_VALUES",
    "VIEW_PREFIX",
    "DatasetDeleted",
    "DatasetFile",
    "DatasetKind",
    "DatasetOut",
    "DatasetUpdate",
    "DatasetUploaded",
    "IDatasetService",
    "detail_url",
    "download_url",
    "show_url",
]
