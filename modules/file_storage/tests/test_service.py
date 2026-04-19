"""Tests for FileStorageService — validation, hashing, lifecycle, capability dispatch."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import UploadFile
from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.contracts.service import StorageBackend
from file_storage.models import StoredFile
from file_storage.service import (
    ContentTypeNotAllowedError,
    FileStorageService,
    FileTooLargeError,
    RedirectDownload,
    StoredFileNotFoundError,
    StreamDownload,
)
from file_storage.settings import FileStorageSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _upload(name: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(data), headers={"content-type": content_type})  # type: ignore[arg-type]


def _settings(tmp_path, **overrides) -> FileStorageSettings:
    return FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM,
        fs_root_path=str(tmp_path),
        **overrides,
    )


async def test_upload_persists_metadata_and_bytes(tmp_path, db_session: AsyncSession):
    settings = _settings(tmp_path)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    payload = b"hello"
    out = await svc.upload(_upload("note.txt", payload, "text/plain"))

    assert out.filename == "note.txt"
    assert out.content_type == "text/plain"
    assert out.size_bytes == len(payload)
    assert out.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert out.backend == constants.BackendId.FILESYSTEM

    # Backend round-trip
    body = await backend.get(out.key)
    out_bytes = b""
    async for chunk in body:
        out_bytes += chunk
    assert out_bytes == payload


async def test_upload_rejects_oversize(tmp_path, db_session: AsyncSession):
    settings = _settings(tmp_path, max_file_size_bytes=4)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    with pytest.raises(FileTooLargeError):
        await svc.upload(_upload("big.bin", b"way too large"))


async def test_upload_rejects_disallowed_content_type(tmp_path, db_session: AsyncSession):
    settings = _settings(tmp_path, allowed_content_types=["text/plain"])
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    with pytest.raises(ContentTypeNotAllowedError):
        await svc.upload(_upload("evil.exe", b"x", "application/octet-stream"))


async def test_upload_compensates_on_db_failure(tmp_path, db_session: AsyncSession):
    """If the DB write fails, the just-uploaded object must be removed from the backend."""
    settings = _settings(tmp_path)

    deleted_keys: list[str] = []

    class _RecordingBackend(FilesystemBackend):
        async def delete(self, key: str) -> None:  # type: ignore[override]
            deleted_keys.append(key)
            await super().delete(key)

    backend = _RecordingBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    # Patch flush to fail once, succeed thereafter — provokes the compensation path.
    real_flush = db_session.flush
    call_count = {"n": 0}

    async def flaky_flush(*args: Any, **kwargs: Any) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return await real_flush(*args, **kwargs)

    monkeypatched = MonkeyPatch()
    monkeypatched.setattr(db_session, "flush", flaky_flush)
    try:
        with pytest.raises(RuntimeError):
            await svc.upload(_upload("doomed.bin", b"x"))
    finally:
        monkeypatched.undo()

    assert len(deleted_keys) == 1


async def test_list_files_paginates_and_filters_by_user(tmp_path, db_session: AsyncSession):
    settings = _settings(tmp_path)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    for i in range(3):
        await svc.upload(_upload(f"f{i}.bin", f"x{i}".encode()))

    items, total = await svc.list_files(page=1, per_page=2)
    assert total == 3
    assert len(items) == 2

    items_p2, _ = await svc.list_files(page=2, per_page=2)
    assert len(items_p2) == 1


async def test_delete_marks_row_and_removes_object(tmp_path, db_session: AsyncSession):
    settings = _settings(tmp_path)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)

    out = await svc.upload(_upload("doomed.bin", b"x"))
    await svc.delete(out.id)

    # Bytes are gone from the backend.
    assert await backend.exists(out.key) is False

    # Row exists but is_deleted=True (use include_deleted to bypass the soft-delete filter).
    stmt = select(StoredFile).where(StoredFile.id == out.id).execution_options(include_deleted=True)
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.is_deleted is True


async def test_get_missing_raises_not_found(tmp_path, db_session: AsyncSession):
    import uuid

    settings = _settings(tmp_path)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)
    with pytest.raises(StoredFileNotFoundError):
        await svc.get(uuid.uuid4())


async def test_download_dispatches_on_backend_capability(tmp_path, db_session: AsyncSession):
    """The service picks Stream vs Redirect from supports_presigned_url, never from backend_id."""
    settings = _settings(tmp_path)
    backend = FilesystemBackend(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)
    out = await svc.upload(_upload("a.bin", b"x"))

    download = await svc.download(out.id)
    assert isinstance(download, StreamDownload)

    # Swap in a presigning backend; download should now redirect.
    class _PresigningBackend:
        backend_id = "presign-test"
        supports_presigned_url = True

        async def put(self, key, stream, **kwargs): ...
        async def get(self, key):  # pragma: no cover
            async def empty():
                if False:
                    yield b""

            return empty()

        async def delete(self, key): ...
        async def exists(self, key):
            return True

        async def presigned_get_url(self, key, ttl_seconds):
            return f"https://signed/{key}"

    pb: StorageBackend = _PresigningBackend()  # type: ignore[assignment]
    svc.backend = pb
    download2 = await svc.download(out.id)
    assert isinstance(download2, RedirectDownload)
    assert download2.url.startswith("https://signed/")


async def _drain(stream: AsyncIterator[bytes]) -> bytes:
    out = b""
    async for chunk in stream:
        out += chunk
    return out


_unused: Any = None
