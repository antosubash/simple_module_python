"""Multipart-upload half of the filesystem backend (#454).

Parts live under ``<root>/.multipart/<upload_id>/<n>`` with the part's MD5 in a
``<n>.etag`` sidecar, so :meth:`list_parts` never re-reads gigabytes to answer.
:meth:`complete_multipart` concatenates them into the final object through a
temp file and an atomic rename, like :meth:`FilesystemBackend.put`.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles

from file_storage import constants
from file_storage.contracts.service import (
    NotSupportedError,
    ObjectInfo,
    Part,
    StorageBackendError,
    StorageNotFoundError,
)

_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
_ETAG_SUFFIX = ".etag"


class FilesystemMultipartMixin:
    """Mixed into :class:`~file_storage.backends.filesystem.FilesystemBackend`."""

    supports_direct_upload = True
    root: Path

    def _resolve(self, key: str) -> Path:  # provided by the concrete backend
        raise NotImplementedError

    def _parts_dir(self, upload_id: str) -> Path:
        # Upload ids are minted here, but they come back in a URL and a DB row:
        # refuse anything that is not exactly what we issued.
        if not _UPLOAD_ID.match(upload_id):
            raise StorageBackendError(f"Invalid upload id: {upload_id!r}")
        return self.root / constants.FS_MULTIPART_DIR / upload_id

    async def create_multipart(self, key: str, content_type: str) -> str:
        self._resolve(key)  # validates the key before we hand out an id
        upload_id = uuid.uuid4().hex
        self._parts_dir(upload_id).mkdir(parents=True, exist_ok=True)
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
        directory = self._parts_dir(upload_id)
        if not directory.is_dir():
            raise StorageNotFoundError(upload_id)
        target = directory / str(part_no)
        tmp = directory / f"{part_no}.{uuid.uuid4().hex}.tmp"
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        try:
            async with aiofiles.open(tmp, "wb") as fh:
                async for chunk in stream:
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageBackendError(f"Part {part_no} exceeds {max_bytes} bytes.")
                    md5.update(chunk)
                    await fh.write(chunk)
            etag = md5.hexdigest()
            # Etag first: a part is "present" only once its data file is, and the
            # data file is renamed last.
            (directory / f"{part_no}{_ETAG_SUFFIX}").write_text(etag)
            tmp.replace(target)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        return Part(no=part_no, etag=etag, size=size)

    async def list_parts(self, key: str, upload_id: str) -> list[Part]:
        directory = self._parts_dir(upload_id)
        if not directory.is_dir():
            raise StorageNotFoundError(upload_id)
        parts = []
        for path in directory.iterdir():
            if not path.name.isdigit():
                continue  # ``.etag`` sidecars and in-flight ``.tmp`` files
            etag_file = path.with_name(path.name + _ETAG_SUFFIX)
            etag = etag_file.read_text() if etag_file.exists() else ""
            parts.append(Part(no=int(path.name), etag=etag, size=path.stat().st_size))
        return sorted(parts, key=lambda p: p.no)

    async def complete_multipart(self, key: str, upload_id: str, parts: list[Part]) -> None:
        directory = self._parts_dir(upload_id)
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            async with aiofiles.open(tmp, "wb") as out:
                for part in sorted(parts, key=lambda p: p.no):
                    source = directory / str(part.no)
                    if not source.is_file():
                        raise StorageBackendError(f"Part {part.no} is missing.")
                    async with aiofiles.open(source, "rb") as fh:
                        while chunk := await fh.read(constants.DEFAULT_CHUNK_SIZE):
                            await out.write(chunk)
            tmp.replace(path)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        shutil.rmtree(directory, ignore_errors=True)

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        shutil.rmtree(self._parts_dir(upload_id), ignore_errors=True)

    async def head(self, key: str) -> ObjectInfo:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageNotFoundError(key)
        return ObjectInfo(size=path.stat().st_size)
