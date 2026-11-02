"""Storage location changes require coordinated restarts (#691)."""

import pytest


@pytest.mark.parametrize(
    "name",
    [
        "backend",
        "fs_root_path",
        "s3_bucket",
        "s3_region",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_endpoint_url",
        "s3_public_endpoint_url",
        "s3_signature_version",
    ],
)
def test_backend_construction_fields_advertise_restart(name):
    from file_storage.settings import FileStorageSettings
    from settings._module_settings import _field_view

    field = _field_view(name, FileStorageSettings(), "SM_FILE_STORAGE_")
    assert field.requires_restart is True


async def test_health_check_reads_current_backend(tmp_path):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from file_storage.backends.filesystem import FilesystemBackend
    from file_storage.health import build_backend_check
    from simple_module_core.health import HealthStatus

    app = FastAPI()
    app.state.file_storage = SimpleNamespace(backend=None)
    check = build_backend_check(app)
    assert (await check()).status == HealthStatus.UNHEALTHY
    app.state.file_storage.backend = FilesystemBackend(root=tmp_path)
    assert (await check()).status == HealthStatus.HEALTHY


async def test_root_change_applies_after_backend_restart(
    authenticated_client, storage, tmp_path, checksum_calls
):
    from file_storage.backends import build_backend
    from file_storage.backends.filesystem import FilesystemBackend

    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    storage.settings.fs_root_path = str(old_root)
    storage.backend = FilesystemBackend(root=old_root)
    original_backend = storage.backend
    response = await authenticated_client.put(
        "/api/settings/modules/file_storage", json={"fs_root_path": str(new_root)}
    )
    assert response.status_code == 200, response.text
    assert storage.backend is original_backend
    response = await authenticated_client.post(
        "/api/file-storage/upload", files={"file": ("before.txt", b"before restart", "text/plain")}
    )
    assert response.status_code == 201, response.text
    assert [p.read_bytes() for p in old_root.rglob("*.txt")] == [b"before restart"]
    assert not new_root.exists()

    # Simulate startup constructing the backend from the newly hydrated settings.
    storage.backend = build_backend(storage.settings)
    response = await authenticated_client.post(
        "/api/file-storage/upload", files={"file": ("after.txt", b"after restart", "text/plain")}
    )
    assert response.status_code == 201, response.text
    assert [p.read_bytes() for p in new_root.rglob("*.txt")] == [b"after restart"]
