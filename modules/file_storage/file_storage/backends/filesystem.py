"""Filesystem storage backend — writes objects under a configurable root."""

from __future__ import annotations

import contextlib
import os
import stat
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path, PureWindowsPath

from file_storage.backends import _fs_confined, register_backend
from file_storage.backends._fs_confined import FileStream, atomic_file, directory, working_directory
from file_storage.backends._io import _io
from file_storage.backends.filesystem_multipart import FilesystemMultipartMixin
from file_storage.contracts.service import (
    NotSupportedError,
    StorageBackendError,
    StorageNotFoundError,
)
from file_storage.core import constants
from file_storage.core.settings import FileStorageSettings


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
        shard = key[:2] if len(key) >= 2 else "_"
        if (
            not key
            or "\\" in key
            or key.startswith("/")
            or PureWindowsPath(key).drive
            or shard == ".."
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in key)
            or any(seg in {".", ".."} for seg in key.split("/"))
        ):
            raise StorageBackendError(f"Invalid storage key: {key!r}")
        try:
            root = self.root.resolve()
            candidate = (root / shard / key).resolve()
        except (OSError, RuntimeError, UnicodeError) as exc:
            raise StorageBackendError(f"Invalid storage key: {key!r}") from exc
        if not candidate.is_relative_to(root) or candidate == root:
            raise StorageBackendError(f"Invalid storage key: {key!r}")
        return candidate

    async def put(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        *,
        content_type: str,
        size: int,
    ) -> None:
        parts, name = await _io(self._location, key)
        # Publish only a fully written object, without re-resolving its parent.
        async with (
            working_directory(self.root, parts, create=True) as parent,
            atomic_file(parent, name) as file,
        ):
            async for chunk in stream:
                await _io(file.write, chunk)

    def _location(self, key: str) -> tuple[tuple[str, ...], str]:
        path = self._resolve(key)  # Preserve #1266's validation on every operation.
        if _fs_confined.CONFINED:
            shard = key[:2] if len(key) >= 2 else "_"
            relative = Path(shard) / key
        else:
            relative = path.relative_to(self.root.resolve())
        return relative.parts[:-1], relative.name

    async def _read(self, key: str, start: int = 0, length: int | None = None) -> FileStream:
        body = FileStream(length)
        try:
            parts, name = await _io(self._location, key)
            await _io(body.open, self.root, parts, name, start)
        except BaseException as exc:
            await body.aclose()
            if isinstance(exc, FileNotFoundError):
                raise StorageNotFoundError(key) from exc
            raise
        return body

    async def get(self, key: str) -> AsyncIterator[bytes]:
        return await self._read(key)

    async def get_range(self, key: str, start: int, end: int) -> AsyncIterator[bytes]:
        return await self._read(key, start, end - start + 1)

    async def delete(self, key: str) -> None:
        parts, name = await _io(self._location, key)
        with contextlib.suppress(FileNotFoundError):
            async with working_directory(self.root, parts) as parent:
                await _io(parent.unlink, name)

    async def list_stale_objects(self, cutoff: datetime) -> AsyncIterator[str]:
        """Yield keys last modified before the reconciliation cutoff."""
        keys = await _io(self._collect_stale_objects, cutoff.timestamp())
        for key in keys:
            yield key

    def _collect_stale_objects(self, cutoff_ts: float) -> list[str]:
        if not _fs_confined.CONFINED:
            return self._collect_stale_paths(cutoff_ts)
        keys: list[str] = []

        def walk(parent, relative: tuple[str, ...]) -> None:
            for name in parent.names():
                if not relative and name == constants.FS_MULTIPART_DIR:
                    continue
                with contextlib.suppress(FileNotFoundError, StorageBackendError):
                    info = parent.stat(name)
                    path = (*relative, name)
                    if stat.S_ISDIR(info.st_mode):
                        with parent.child(name) as child:
                            walk(child, path)
                    elif stat.S_ISREG(info.st_mode) and len(path) >= 3:
                        key = "/".join(path[1:])
                        parts, filename = self._location(key)
                        if (*parts, filename) == path and info.st_mtime < cutoff_ts:
                            keys.append(key)

        with contextlib.suppress(FileNotFoundError), directory(self.root) as root:
            walk(root, ())
        return keys

    def _collect_stale_paths(self, cutoff_ts: float) -> list[str]:
        keys = []
        for folder, dirs, files in os.walk(self.root):
            if Path(folder) == self.root:
                dirs[:] = [name for name in dirs if name != constants.FS_MULTIPART_DIR]
            for name in files:
                path = Path(folder) / name
                relative = path.relative_to(self.root)
                # Preserve the previous shard/key-directory/file glob depth.
                if len(relative.parts) < 3:
                    continue
                key = relative.as_posix().split("/", 1)[1]
                # A concurrent delete may have removed a variant during the scan.
                with contextlib.suppress(FileNotFoundError, StorageBackendError):
                    if self._resolve(key) != path.resolve():
                        continue
                    if path.is_file() and path.stat().st_mtime < cutoff_ts:
                        keys.append(key)
        return keys

    async def exists(self, key: str) -> bool:
        parts, name = await _io(self._location, key)
        try:
            async with working_directory(self.root, parts) as parent:
                return stat.S_ISREG((await _io(parent.stat, name)).st_mode)
        except FileNotFoundError:
            return False

    async def presigned_get_url(
        self,
        key: str,
        ttl_seconds: int,
        *,
        content_disposition: str | None = None,
        content_type: str | None = None,
    ) -> str:
        raise NotSupportedError("Filesystem backend cannot mint presigned URLs.")


@register_backend(constants.BackendId.FILESYSTEM)
def _build(settings: FileStorageSettings) -> FilesystemBackend:
    return FilesystemBackend(root=settings.resolved_fs_root())
