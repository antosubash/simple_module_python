"""File events expose durable state to independent readers (#1079)."""

import pytest
from _file_storage_uploads_support import API, open_session, upload_all
from file_storage.contracts.events import FileDeleted, FileUploaded
from file_storage.models import StoredFile
from simple_module_db import all_tenants


@pytest.fixture
def settings(settings, tmp_path):
    settings.database_url = f"sqlite+aiosqlite:///{tmp_path / 'events.db'}"
    return settings


@pytest.mark.parametrize("multipart", [False, True])
@pytest.mark.parametrize("bulk", [False, True])
async def test_upload_and_delete_events_observe_committed_rows(
    app, authenticated_client, storage, checksum_calls, multipart, bulk
):
    seen = []

    async def observe(event):
        with all_tenants():
            async with app.state.sm.db.session_factory() as db:
                row = await db.get(StoredFile, event.file_id)
                seen.append((type(event), row is not None))

    app.state.sm.event_bus.subscribe(FileUploaded, observe)
    app.state.sm.event_bus.subscribe(FileDeleted, observe)
    if multipart:
        opened = await open_session(authenticated_client, total=2)
        assert opened.status_code == 201, opened.text
        upload_id = opened.json()["id"]
        etags = await upload_all(authenticated_client, upload_id, b"hi")
        response = await authenticated_client.post(
            f"{API}/uploads/{upload_id}/complete",
            json={"parts": [{"n": n, "etag": e} for n, e in etags.items()]},
        )
        assert response.status_code == 200, response.text
        file_id = response.json()["file"]["id"]
    else:
        response = await authenticated_client.post(
            f"{API}/upload", files={"file": ("test.txt", b"hi", "text/plain")}
        )
        assert response.status_code == 201, response.text
        file_id = response.json()["id"]
    assert seen == [(FileUploaded, True)]
    if bulk:
        deleted = await authenticated_client.post(
            f"{API}/files/bulk-delete", json={"ids": [file_id]}
        )
        assert deleted.status_code == 200, deleted.text
    else:
        assert (await authenticated_client.delete(f"{API}/files/{file_id}")).status_code == 204
    assert seen == [(FileUploaded, True), (FileDeleted, False)]
