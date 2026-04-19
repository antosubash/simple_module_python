"""Dataset service: orchestrates DB rows, backend IO, and metadata extraction.

Bytes live in a ``file_storage.StorageBackend`` — the datasets module does
not own any filesystem of its own. That hands S3 / GCS / Azure support to
every consumer for free the moment the host swaps ``SM_FILE_STORAGE_BACKEND``.
"""

from __future__ import annotations

import contextlib
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from file_storage.contracts.service import StorageBackend, StorageNotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datasets.contracts.files import DatasetFile
from datasets.contracts.schemas import DatasetOut, DatasetUpdate
from datasets.extractors import extract_metadata, kind_for_filename
from datasets.models import Dataset


@dataclass
class UploadInput:
    """Inputs for ``DatasetService.register_upload``.

    The endpoint streams the upload to ``temp_path`` first so this layer
    can extract metadata from a local file (fiona/rasterio need a path),
    then upload the bytes to the storage backend and persist the row.
    """

    name: str
    original_filename: str
    temp_path: Path
    size_bytes: int
    mime_type: str | None
    description: str | None = None
    kind: str | None = None


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "dataset"


def safe_filename(name: str) -> str:
    """Return a filename safe to log / surface in URLs."""
    base = Path(name).name or "upload.bin"
    cleaned = _UNSAFE_NAME_RE.sub("_", base).strip("._") or "upload.bin"
    return cleaned[:200]


def _storage_key(dataset_id: int, original_filename: str) -> str:
    """Build a backend key scoped under ``datasets/``.

    The ``datasets/`` prefix keeps dataset bytes discoverable alongside
    other file_storage tenants (e.g. the generic StoredFile uploads)
    without namespace collisions. A uuid suffix guarantees uniqueness
    even when a dataset is re-uploaded under the same id.
    """
    suffix = Path(original_filename).suffix.lower()
    return f"datasets/{dataset_id}/{uuid.uuid4().hex}{suffix}"


async def _file_stream(path: Path, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            yield chunk


class DatasetService:
    """CRUD + upload orchestration for datasets.

    Downstream modules should depend on the ``IDatasetService`` Protocol
    (see ``datasets.contracts.service``) rather than this concrete class,
    and obtain an instance via ``datasets.deps.get_dataset_service``.
    """

    def __init__(self, db: AsyncSession, backend: StorageBackend) -> None:
        self.db = db
        self.backend = backend

    # ── Lookups ──────────────────────────────────────────────────────

    async def get_all(self) -> list[DatasetOut]:
        result = await self.db.execute(select(Dataset).order_by(Dataset.id.desc()))
        return [DatasetOut.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, dataset_id: int) -> DatasetOut | None:
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return None
        return DatasetOut.model_validate(entity)

    async def get_by_slug(self, slug: str) -> DatasetOut | None:
        result = await self.db.execute(select(Dataset).where(Dataset.slug == slug))
        entity = result.scalar_one_or_none()
        if entity is None:
            return None
        return DatasetOut.model_validate(entity)

    async def list_by_kind(self, kind: str, *, limit: int | None = None) -> list[DatasetOut]:
        stmt = select(Dataset).where(Dataset.kind == kind).order_by(Dataset.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [DatasetOut.model_validate(row) for row in result.scalars()]

    # ── File access ──────────────────────────────────────────────────

    async def get_file(self, dataset_id: int) -> DatasetFile | None:
        entity = await self.db.get(Dataset, dataset_id)
        if entity is None:
            return None
        return DatasetFile(
            metadata=DatasetOut.model_validate(entity),
            storage_key=entity.storage_key,
            original_filename=entity.original_filename,
            mime_type=entity.mime_type,
            _backend=self.backend,
        )

    # ── Upload ───────────────────────────────────────────────────────

    async def register_upload(self, payload: UploadInput) -> DatasetOut:
        """Persist a dataset row, extract metadata, then upload the temp
        file's bytes to the storage backend keyed by the new row's id."""
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
            storage_key="",  # filled in once we have entity.id
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

        storage_key = _storage_key(entity.id, payload.original_filename)
        try:
            await self.backend.put(
                storage_key,
                _file_stream(payload.temp_path),
                content_type=payload.mime_type or "application/octet-stream",
                size=payload.size_bytes,
            )
        except Exception:
            await self.db.delete(entity)
            await self.db.flush()
            raise

        entity.storage_key = storage_key
        await self.db.flush()
        await self.db.refresh(entity)
        return DatasetOut.model_validate(entity)

    # ── Mutations ────────────────────────────────────────────────────

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
        # Delete the object last so a DB rollback can't orphan metadata
        # pointing at already-removed bytes. Missing objects are fine.
        if storage_key:
            with contextlib.suppress(StorageNotFoundError):
                await self.backend.delete(storage_key)
        return True

    # ── Internal ─────────────────────────────────────────────────────

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


__all__ = ["DatasetService", "UploadInput", "safe_filename", "slugify"]
