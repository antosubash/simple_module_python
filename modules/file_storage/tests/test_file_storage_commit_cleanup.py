"""Storage bytes survive a failed request commit (#582)."""

from unittest.mock import AsyncMock

import pytest
from file_storage import thumbnails
from simple_module_db.session import RequestSession


@pytest.mark.parametrize("bulk", [False, True])
async def test_delete_commit_failure_keeps_bytes(authenticated_client, storage, monkeypatch, bulk):
    uploaded = await authenticated_client.post(
        "/api/file-storage/upload", files={"file": ("a.txt", b"payload", "text/plain")}
    )
    assert uploaded.status_code == 201
    row = uploaded.json()
    variant = thumbnails.variant_key(row["key"], 128)

    async def body():
        yield b"thumbnail"

    await storage.backend.put(variant, body(), content_type="image/webp", size=9)
    with monkeypatch.context() as patch:
        patch.setattr(RequestSession, "commit", AsyncMock(side_effect=RuntimeError("commit")))
        if bulk:
            response = await authenticated_client.post(
                "/api/file-storage/files/bulk-delete", json={"ids": [row["id"]]}
            )
        else:
            response = await authenticated_client.delete(f"/api/file-storage/files/{row['id']}")
    assert response.status_code == 500
    assert await storage.backend.exists(row["key"])
    assert await storage.backend.exists(variant)
    response = await authenticated_client.get(f"/api/file-storage/files/{row['id']}/download")
    assert response.status_code == 200
    assert response.content == b"payload"
