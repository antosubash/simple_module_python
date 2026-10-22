"""Filesystem storage backend — writes objects under a configurable root."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import aiofiles

from file_storage import constants
from file_storage.backends import register_backend
from file_storage.backends.filesystem_multipart import FilesystemMultipartMixin
from file_storage.contracts.service import (
    NotSupportedError,
    StorageBackendError,
    StorageNotFoundError,
)
from file_storage.settings import FileStorageSettings


class FilesystemBackend(FilesystemMultipartMixin):
    """Stores objects on the local filesystem under ``root``.

    Keys are sharded by their first two characters to keep any single
    directory from accumulating millions of entries (which slows ``readdir``
    on most filesystems). A key like ``2026/04/19/abc123.png`` is written to
    ``<root>/20/2026/04/19/abc123.png``.
    """

    backend_id = constants.BackendId.FILESYSTEM
    supports_presigned_url = False

    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, key: str) -> Path:
        # Reject path traversal: ".." segments and absolute paths can escape root.
        if key.startswith("/") or ".." in Path(key).parts:
            raise StorageBackendError(f"Invalid storage key: {key!r}")
        shard = key[:2] if len(key) >= 2 else "_"
        return self.root / shard / key

    async def put(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        *,
        content_type: str,
        size: int,
    ) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename into place: a concurrent ``get`` (a
        # thumbnail cache hit mid-generation) must never see a half-written
        # object, and a crash must not leave a truncated one behind.
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            async with aiofiles.open(tmp, "wb") as fh:
                async for chunk in stream:
                    await fh.write(chunk)
            tmp.replace(path)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    def _existing(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.exists():
            raise StorageNotFoundError(key)
        return path

    async def get(self, key: str) -> AsyncIterator[bytes]:
        return _stream_file(self._existing(key))

    async def get_range(self, key: str, start: int, end: int) -> AsyncIterator[bytes]:
        return _stream_file(self._existing(key), start=start, length=end - start + 1)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)

    async def list_stale_objects(self, cutoff: datetime) -> AsyncIterator[str]:
        """Yield keys last modified before the reconciliation cutoff."""
        cutoff_ts = cutoff.timestamp()
        for path in self.root.glob("*/*/**/*"):
            # Another delete (including this sweep) may have removed a variant.
            with contextlib.suppress(FileNotFoundError):
                if path.is_file() and path.stat().st_mtime < cutoff_ts:
                    yield path.relative_to(self.root).as_posix().split("/", 1)[1]

    async def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    async def presigned_get_url(
        self,
        key: str,
        ttl_seconds: int,
        *,
        content_disposition: str | None = None,
        content_type: str | None = None,
    ) -> str:
        raise NotSupportedError("Filesystem backend cannot mint presigned URLs.")


async def _stream_file(
    path: Path, *, start: int = 0, length: int | None = None
) -> AsyncIterator[bytes]:
    """Yield ``length`` bytes from ``start`` (to EOF when ``None``), chunk by chunk."""
    remaining = length
    async with aiofiles.open(path, "rb") as fh:
        await fh.seek(start)
        while remaining is None or remaining > 0:
            size = constants.DEFAULT_CHUNK_SIZE
            if remaining is not None:
                size = min(size, remaining)
            chunk = await fh.read(size)
            if not chunk:
                break
            if remaining is not None:
                remaining -= len(chunk)
            yield chunk


@register_backend(constants.BackendId.FILESYSTEM)
def _build(settings: FileStorageSettings) -> FilesystemBackend:
    return FilesystemBackend(root=settings.resolved_fs_root())
