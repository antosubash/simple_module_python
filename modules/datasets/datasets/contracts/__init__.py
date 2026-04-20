"""Datasets contracts — public interface for other modules.

Downstream modules should import from here, not from
``datasets.models`` or ``datasets.service`` internals. The SM009
diagnostic enforces framework→plugin purity; this package is the
supported surface for plugin→plugin coupling::

    from datasets.contracts import (
        DatasetOut,            # DTO returned by service lookups
        DatasetFile,           # handle for stored file access
        DatasetUploaded,       # event subscribers listen for
        download_url,          # URL helper for UIs
    )

For the FastAPI dependency, prefer
``from datasets.deps import DatasetServiceDep``. Type-hint against the
concrete ``DatasetService`` — the module is single-impl, so there's no
Protocol abstraction (matching the framework's "ship a Protocol only
for real extension points" rule).
"""

from datasets.contracts.events import DatasetDeleted, DatasetUploaded
from datasets.contracts.files import DatasetFile
from datasets.contracts.schemas import (
    KIND_VALUES,
    DatasetKind,
    DatasetOut,
    DatasetUpdate,
)
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
    "detail_url",
    "download_url",
    "show_url",
]
