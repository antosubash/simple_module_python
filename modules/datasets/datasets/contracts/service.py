"""Dataset service protocol — the public contract other modules depend on.

Downstream modules should type-hint against ``IDatasetService`` and depend
on the concrete ``DatasetService`` via ``datasets.deps.get_dataset_service``
(or the ``DatasetServiceDep`` annotated alias). That keeps the consuming
module from reaching into Datasets-internal modules (``datasets.models``,
``datasets.storage``) — such imports are flagged by the SM009 diagnostic.
"""

from __future__ import annotations

from typing import Protocol

from datasets.contracts.files import DatasetFile
from datasets.contracts.schemas import DatasetOut, DatasetUpdate


class IDatasetService(Protocol):
    """Interface for dataset operations exposed to other modules."""

    # ── Lookups ──────────────────────────────────────────────────────
    async def get_all(self) -> list[DatasetOut]: ...
    async def get_by_id(self, dataset_id: int) -> DatasetOut | None: ...
    async def get_by_slug(self, slug: str) -> DatasetOut | None: ...
    async def list_by_kind(self, kind: str, *, limit: int | None = None) -> list[DatasetOut]: ...

    # ── File access ──────────────────────────────────────────────────
    async def get_file(self, dataset_id: int) -> DatasetFile | None:
        """Return an opaque handle to the stored file plus its metadata.

        Consumers that need to parse the raw bytes (e.g. a tile renderer,
        a reprojection job, or a stats worker) should prefer this over
        reading storage directly — it survives future storage backend
        swaps.
        """
        ...

    # ── Mutations ────────────────────────────────────────────────────
    async def update(self, dataset_id: int, data: DatasetUpdate) -> DatasetOut | None: ...
    async def delete(self, dataset_id: int) -> bool: ...
