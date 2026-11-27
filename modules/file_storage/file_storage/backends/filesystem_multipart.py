"""Multipart filesystem uploads, confined like ordinary objects (#454, #1269).

Parts live under ``<root>/.multipart/<upload_id>/<n>`` with MD5 ETag sidecars,
so listing parts never needs to re-read their contents. Completion concatenates
parts through a temporary file and atomically replaces the final object.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import stat
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from file_storage.backends._fs_confined import (
    atomic_file,
    directory,
    opened_file,
    working_directory,
)
from file_storage.backends._io import _io
from file_storage.contracts.service import (
    NotSupportedError,
    ObjectInfo,
    Part,
    StorageBackendError,
    StorageNotFoundError,
)
from file_storage.core import constants

_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
_ETAG_SUFFIX = ".etag"


class FilesystemMultipartMixin:
    """Mixed into :class:`~file_storage.backends.filesystem.FilesystemBackend`."""

    supports_direct_upload = True
    root: Path

    def _resolve(self, key: str) -> Path:  # provided by the concrete backend
        raise NotImplementedError

    def _location(self, key: str) -> tuple[tuple[str, ...], str]:
        raise NotImplementedError

    def _parts_dir(self, upload_id: str) -> Path:
        # Upload ids come back in URLs and DB rows; accept only those we mint.
        if not _UPLOAD_ID.fullmatch(upload_id):
            raise StorageBackendError(f"Invalid upload id: {upload_id!r}")
        return self.root / constants.FS_MULTIPART_DIR / upload_id

    def _parts_location(self, upload_id: str) -> tuple[str, ...]:
        return self._parts_dir(upload_id).relative_to(self.root).parts

    async def create_multipart(self, key: str, content_type: str) -> str:
        await _io(self._resolve, key)
        upload_id = uuid.uuid4().hex
        async with working_directory(self.root, self._parts_location(upload_id), create=True):
            pass
        return upload_id

    async def presign_part(
        self, key: str, upload_id: str, part_no: int, ttl: int, size: int | None = None
    ) -> str:
        raise NotSupportedError("Filesystem parts are uploaded through the app.")

    async def presigned_put_url(self, key: str, ttl: int, content_type: str) -> str:
        raise NotSupportedError("Filesystem backend cannot mint presigned URLs.")

    async def write_part(
        self,
        key: str,
        upload_id: str,
        part_no: int,
        stream: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> Part:
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        try:
            async with (
                working_directory(self.root, self._parts_location(upload_id)) as parent,
                atomic_file(parent, str(part_no)) as file,
            ):
                async for chunk in stream:
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageBackendError(f"Part {part_no} exceeds {max_bytes} bytes.")
                    md5.update(chunk)
                    await _io(file.write, chunk)
                etag = md5.hexdigest()
                # Publish the ETag before data makes the part visible.
                async with atomic_file(parent, f"{part_no}{_ETAG_SUFFIX}") as sidecar:
                    await _io(sidecar.write, etag.encode())
        except FileNotFoundError as exc:
            raise StorageNotFoundError(upload_id) from exc
        return Part(no=part_no, etag=etag, size=size)

    async def list_parts(self, key: str, upload_id: str) -> list[Part]:
        return await _io(self._list_parts, upload_id)

    def _list_parts(self, upload_id: str) -> list[Part]:
        parts = []
        try:
            with directory(self.root, self._parts_location(upload_id)) as parent:
                for name in parent.names():
                    if not name.isdigit():
                        continue  # ETag sidecars and in-flight temporary files.
                    info = parent.stat(name)
                    if not stat.S_ISREG(info.st_mode):
                        raise StorageBackendError("Multipart part is not a regular file.")
                    etag = ""
                    with (
                        contextlib.suppress(FileNotFoundError),
                        parent.open(name + _ETAG_SUFFIX) as sidecar,
                    ):
                        etag = sidecar.read().decode()
                    parts.append(Part(no=int(name), etag=etag, size=info.st_size))
        except FileNotFoundError as exc:
            raise StorageNotFoundError(upload_id) from exc
        return sorted(parts, key=lambda p: p.no)

    async def complete_multipart(self, key: str, upload_id: str, parts: list[Part]) -> None:
        location, name = await _io(self._location, key)
        try:
            async with (
                working_directory(self.root, self._parts_location(upload_id)) as source,
                working_directory(self.root, location, create=True) as target,
                atomic_file(target, name) as out,
            ):
                for part in sorted(parts, key=lambda p: p.no):
                    async with opened_file(source, str(part.no)) as file:
                        while chunk := await _io(file.read, constants.DEFAULT_CHUNK_SIZE):
                            await _io(out.write, chunk)
        except FileNotFoundError as exc:
            raise StorageBackendError("Multipart part is missing.") from exc
        await self.abort_multipart(key, upload_id)

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        self._parts_location(upload_id)  # Validate before a missing scratch root can mask it.
        with contextlib.suppress(FileNotFoundError):
            async with working_directory(self.root, (constants.FS_MULTIPART_DIR,)) as parent:
                await _io(parent.remove_child, upload_id)

    async def head(self, key: str) -> ObjectInfo:
        parts, name = await _io(self._location, key)
        try:
            async with working_directory(self.root, parts) as parent:
                info = await _io(parent.stat, name)
                if not stat.S_ISREG(info.st_mode):
                    raise StorageNotFoundError(key)
                return ObjectInfo(size=info.st_size)
        except FileNotFoundError as exc:
            raise StorageNotFoundError(key) from exc
