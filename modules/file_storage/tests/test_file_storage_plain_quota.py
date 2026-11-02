"""Plain uploads share stored-byte limits and resumable reservations (#586)."""

from file_storage import constants
from file_storage_uploads_helpers import API, open_session


async def upload(client, size):
    return await client.post(
        f"{API}/upload", files={"file": ("small.bin", b"x" * size, "application/octet-stream")}
    )


async def test_plain_uploads_enforce_aggregate_quota(authenticated_client, storage):
    storage.settings.quota_bytes = 10
    assert (await upload(authenticated_client, 6)).status_code == 201
    assert (await upload(authenticated_client, 4)).status_code == 201
    rejected = await upload(authenticated_client, 1)
    assert rejected.status_code == 413
    assert rejected.json()["detail"]["code"] == constants.ErrorCode.QUOTA_EXCEEDED
    listing = (await authenticated_client.get(f"{API}/files")).json()
    assert listing["total"] == 2
    assert len([p for p in storage.backend.root.rglob("*") if p.is_file()]) == 2


async def test_plain_upload_honors_reservations_and_abort_releases_them(
    authenticated_client, storage, checksum_calls
):
    storage.settings.quota_bytes = 10
    response = await open_session(authenticated_client, total=8)
    assert response.status_code == 201
    assert (await upload(authenticated_client, 3)).status_code == 413
    assert (await upload(authenticated_client, 2)).status_code == 201
    await authenticated_client.delete(f"{API}/uploads/{response.json()['id']}")
    assert (await upload(authenticated_client, 8)).status_code == 201


async def test_platform_quota_counts_only_platform_files(db_session, tmp_path):
    from io import BytesIO

    import pytest
    from fastapi import UploadFile
    from file_storage.backends.filesystem import FilesystemBackend
    from file_storage.service import FileStorageService
    from file_storage.settings import FileStorageSettings
    from file_storage.upload_support import QuotaExceededError
    from simple_module_db import tenant_context

    backend = FilesystemBackend(root=tmp_path)
    service = FileStorageService(db_session, backend, FileStorageSettings(quota_bytes=3))

    def file(size):
        return UploadFile(BytesIO(b"x" * size), filename="small.bin")

    with tenant_context("tenant-a"):
        await service.upload(file(3))
    await service.upload(file(3), platform=True)
    with pytest.raises(QuotaExceededError):
        await service.upload(file(1), platform=True)
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 2
