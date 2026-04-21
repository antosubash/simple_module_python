"""Public-facing value types for dataset file access.

Consumers that depend on the Datasets module import ``DatasetFile`` rather
than the private ``Dataset`` SQLModel table. It carries enough to stream
bytes, hand off to a parser library, or materialise to a local path
without a second round-trip.

Because the datasets module delegates bytes storage to
``file_storage.StorageBackend``, a dataset's bytes may live on any
backend (local FS today, S3 or GCS tomorrow). ``DatasetFile`` hides that
difference: consumers call :meth:`stream` or :meth:`materialize_to` and
never touch backend-specific APIs.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from datasets.contracts.schemas import DatasetOut

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend


@dataclass(frozen=True)
class DatasetFile:
    """Read-only handle to a stored dataset file.

    The handle is decoupled from any specific storage backend. Consumers
    that need bytes use :meth:`stream` (async iterator) or :meth:`read`
    (``bytes``). Consumers that need a filesystem path — e.g. to hand
    the file off to ``fiona`` / ``rasterio`` / ``pandas`` that require
    ``str(path)`` — use :meth:`materialize_to`.
    """

    metadata: DatasetOut
    storage_key: str
    original_filename: str
    mime_type: str | None
    # Backend injected by the service — not part of the printable repr.
    _backend: StorageBackend

    async def stream(self) -> AsyncIterator[bytes]:
        """Yield the file's bytes in chunks. Works on any backend."""
        return await self._backend.get(self.storage_key)

    async def read(self) -> bytes:
        """Read the entire file into memory. Prefer :meth:`stream` for large files."""
        buf = bytearray()
        async for chunk in await self._backend.get(self.storage_key):
            buf.extend(chunk)
        return bytes(buf)

    async def exists(self) -> bool:
        return await self._backend.exists(self.storage_key)

    async def materialize_to(self, path: Path) -> Path:
        """Download the file to ``path``. Returns the path.

        Use for libraries that require a filesystem path (``fiona``,
        ``rasterio``, ``pandas.read_csv``). For the filesystem backend
        this is almost free; for S3 it pulls bytes down once. Callers
        are responsible for deleting the file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fp:
            async for chunk in await self._backend.get(self.storage_key):
                fp.write(chunk)
        return path

    async def materialize_to_tempfile(self, suffix: str | None = None) -> Path:
        """Download to a named temp file. Returns the path.

        Convenience wrapper around :meth:`materialize_to` for the common
        "I need a Path for fiona/rasterio, then I'll delete it" pattern.
        Caller must ``unlink`` the returned path.
        """
        effective_suffix = suffix if suffix is not None else Path(self.original_filename).suffix
        fd, tmp = tempfile.mkstemp(suffix=effective_suffix)
        # We don't need the file descriptor — ``materialize_to`` re-opens the path.
        import os

        os.close(fd)
        return await self.materialize_to(Path(tmp))
