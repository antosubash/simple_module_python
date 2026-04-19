"""Filesystem storage backend — writes objects under a configurable root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles

from file_storage import constants
from file_storage.backends import register_backend
from file_storage.contracts.service import (
    NotSupportedError,
    StorageBackendError,
    StorageNotFoundError,
)
from file_storage.settings import FileStorageSettings


class FilesystemBackend:
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
        async with aiofiles.open(path, "wb") as fh:
            async for chunk in stream:
                await fh.write(chunk)

    async def get(self, key: str) -> AsyncIterator[bytes]:
        path = self._resolve(key)
        if not path.exists():
            raise StorageNotFoundError(key)
        return _stream_file(path)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    async def presigned_get_url(self, key: str, ttl_seconds: int) -> str:
        raise NotSupportedError("Filesystem backend cannot mint presigned URLs.")


async def _stream_file(path: Path) -> AsyncIterator[bytes]:
    async with aiofiles.open(path, "rb") as fh:
        while True:
            chunk = await fh.read(constants.DEFAULT_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


@register_backend(constants.BackendId.FILESYSTEM)
def _build(settings: FileStorageSettings) -> FilesystemBackend:
    return FilesystemBackend(root=settings.resolved_fs_root())
