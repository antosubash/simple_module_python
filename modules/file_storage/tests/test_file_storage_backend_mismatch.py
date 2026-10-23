"""Rows from a previous provider must never use the active provider (#589)."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from file_storage import constants, thumbnails
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings


@pytest.mark.parametrize(
    ("backend", "row"),
    [
        (SimpleNamespace(), SimpleNamespace(backend="filesystem")),
        (SimpleNamespace(backend_id="filesystem"), SimpleNamespace()),
        (
            SimpleNamespace(backend_id="filesystem"),
            SimpleNamespace(backend="filesystem"),
        ),
    ],
)
def test_guard_allows_missing_or_matching_identity(backend, row):
    from file_storage.backend_guard import require_backend

    require_backend(backend, row)


@pytest.fixture
async def mismatched(db_session, tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    service = FileStorageService(db_session, backend, FileStorageSettings())
    out = await service.upload(UploadFile(filename="old.png", file=BytesIO(b"original")))
    row = await service.get(out.id)
    row.backend = constants.BackendId.S3
    await db_session.flush()
    return service, row


@pytest.mark.parametrize("operation", ["stream", "redirect", "metadata", "thumbnail"])
async def test_old_provider_reads_are_refused(mismatched, operation, monkeypatch):
    from file_storage.backend_guard import BackendUnavailableError

    service, row = mismatched
    service.backend.get = AsyncMock(side_effect=AssertionError("wrong store"))
    service.backend.presigned_get_url = AsyncMock(side_effect=AssertionError("wrong store"))
    monkeypatch.setattr(
        thumbnails, "get_or_create", AsyncMock(side_effect=AssertionError("wrong store"))
    )
    if operation == "redirect":
        service.backend.supports_presigned_url = True
    with pytest.raises(BackendUnavailableError):
        if operation == "thumbnail":
            await service.thumbnail(row, 128)
        else:
            await service.download(row.id, open_body=operation != "metadata")


@pytest.mark.parametrize("bulk", [False, True])
async def test_old_provider_delete_keeps_objects(mismatched, bulk, caplog):
    service, row = mismatched
    service.backend.delete = AsyncMock(side_effect=AssertionError("wrong store"))
    if bulk:
        await service.delete_many([row.id])
    else:
        await service.delete(row.id)
    assert row.is_deleted
    service.backend.delete.assert_not_awaited()
    assert "backend_mismatch" in caplog.text


@pytest.mark.parametrize(
    "path", ["files/{id}/download", "files/{id}/thumbnail", "public/{id}", "public/{id}/thumbnail"]
)
async def test_old_provider_http_conflict(authenticated_client, storage, path):
    response = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}/upload",
        files={"file": ("a.png", b"image", "image/png")},
        data={"public": "true"},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    file_id = uploaded["id"]
    suffix = "-w256" if path.endswith("thumbnail") else ""
    etag = f'"{uploaded["checksum_sha256"]}{suffix}"'
    # Change provider identity while retaining the same objects to expose any
    # accidental access, including a cached/conditional response.
    storage.backend.backend_id = constants.BackendId.S3
    response = await authenticated_client.get(
        f"{constants.ROUTE_PREFIX_API}/{path.format(id=file_id)}",
        headers={"Range": "bytes=0-1", "If-None-Match": etag},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "file_storage.backend_unavailable",
        "message": "This file is stored on a backend that is no longer configured.",
    }
