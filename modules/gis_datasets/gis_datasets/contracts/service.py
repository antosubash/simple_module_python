"""Dataset service protocol — the public contract other modules depend on."""

from __future__ import annotations

from typing import Protocol

from gis_datasets.contracts.schemas import DatasetOut, DatasetUpdate


class IDatasetService(Protocol):
    """Interface for dataset operations."""

    async def get_all(self) -> list[DatasetOut]: ...
    async def get_by_id(self, dataset_id: int) -> DatasetOut | None: ...
    async def update(self, dataset_id: int, data: DatasetUpdate) -> DatasetOut | None: ...
    async def delete(self, dataset_id: int) -> bool: ...
