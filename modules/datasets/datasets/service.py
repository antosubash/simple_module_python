"""Dataset service: orchestrates DB rows, file storage, and metadata extraction."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datasets.contracts.schemas import DatasetOut, DatasetUpdate
from datasets.extractors import extract_metadata, kind_for_filename
from datasets.models import Dataset
from datasets.storage import LocalDatasetStorage, safe_filename


@dataclass
class UploadInput:
    """Inputs for ``DatasetService.register_upload``.

    The endpoint streams the upload to ``temp_path`` first so this layer can
    extract metadata and choose a final storage key without touching the
    FastAPI ``UploadFile`` (which keeps the service trivially unit-testable).
    """

    name: str
    original_filename: str
    temp_path: Path
    size_bytes: int
    mime_type: str | None
    description: str | None = None
    kind: str | None = None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "dataset"


class DatasetService:
    """CRUD + upload orchestration for datasets."""

    def __init__(self, db: AsyncSession, storage: LocalDatasetStorage) -> None:
        self.db = db
        self.storage = storage

    async def get_all(self) -> list[DatasetOut]:
        result = await self.db.execute(select(Dataset).order_by(Dataset.id.desc()))
        return [DatasetOut.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, dataset_id: int) -> DatasetOut | None:
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return None
        return DatasetOut.model_validate(entity)

    async def get_storage_key(self, dataset_id: int) -> tuple[str, str, str | None] | None:
        """Return (storage_key, original_filename, mime_type) for a download."""
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return None
        return entity.storage_key, entity.original_filename, entity.mime_type

    async def register_upload(self, payload: UploadInput) -> DatasetOut:
        """Persist a dataset row, extract metadata, then move the temp file
        into the storage backend keyed by the new row's id."""
        kind = payload.kind or kind_for_filename(payload.original_filename)
        meta = extract_metadata(payload.temp_path, kind)

        slug = await self._unique_slug(slugify(payload.name))
        entity = Dataset(
            name=payload.name,
            slug=slug,
            kind=kind,
            description=payload.description,
            original_filename=safe_filename(payload.original_filename),
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
            # storage_key is filled in below once we have the row id.
            storage_key="",
            crs=meta.crs,
            bbox_min_x=meta.bbox_min_x,
            bbox_min_y=meta.bbox_min_y,
            bbox_max_x=meta.bbox_max_x,
            bbox_max_y=meta.bbox_max_y,
            feature_count=meta.feature_count,
            band_count=meta.band_count,
            extraction_status=meta.status,
        )
        self.db.add(entity)
        await self.db.flush()  # assigns entity.id

        storage_key = self.storage.key_for(entity.id, payload.original_filename)
        try:
            self._move_into_storage(payload.temp_path, storage_key)
        except OSError as exc:
            await self.db.delete(entity)
            await self.db.flush()
            raise RuntimeError(f"Failed to store upload: {exc}") from exc

        entity.storage_key = storage_key
        await self.db.flush()
        await self.db.refresh(entity)
        return DatasetOut.model_validate(entity)

    def _move_into_storage(self, source: Path, key: str) -> None:
        target = self.storage.absolute(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # ``Path.replace`` fails across filesystems (tempdir vs storage_dir).
        # Falling back to copy+unlink keeps the upload pipeline portable.
        try:
            source.replace(target)
        except OSError:
            shutil.copyfile(source, target)
            source.unlink(missing_ok=True)

    async def update(self, dataset_id: int, data: DatasetUpdate) -> DatasetOut | None:
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.db.flush()
        await self.db.refresh(entity)
        return DatasetOut.model_validate(entity)

    async def delete(self, dataset_id: int) -> bool:
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return False
        storage_key = entity.storage_key
        await self.db.delete(entity)
        await self.db.flush()
        # Delete the file last so a DB rollback doesn't leave orphan rows
        # pointing at an already-removed file.
        if storage_key:
            self.storage.delete(storage_key)
        return True

    async def _unique_slug(self, base: str) -> str:
        candidate = base
        suffix = 2
        while await self._slug_exists(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    async def _slug_exists(self, slug: str) -> bool:
        result = await self.db.execute(select(Dataset.id).where(Dataset.slug == slug))
        return result.scalar_one_or_none() is not None
