"""Multipart uploads remain usable without the optional background_tasks integration."""

import builtins

from file_storage_uploads_helpers import API, open_session, upload_all


async def test_upload_without_background_tasks(app, authenticated_client, storage, monkeypatch):
    monkeypatch.delattr(app.state, "background_tasks", raising=False)
    original_import = builtins.__import__
    attempted = []

    def without_background_tasks(name, *args, **kwargs):
        if name == "background_tasks" or name.startswith("background_tasks."):
            attempted.append(name)
            raise ImportError("background_tasks is not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_background_tasks)
    data = b"upload without a worker"
    created = await open_session(authenticated_client, total=len(data))
    assert created.status_code == 201, created.text
    upload_id = created.json()["id"]
    etags = await upload_all(authenticated_client, upload_id, data)
    done = await authenticated_client.post(
        f"{API}/uploads/{upload_id}/complete",
        json={"parts": [{"n": n, "etag": e} for n, e in etags.items()]},
    )
    assert done.status_code == 200, done.text
    file = done.json()["file"]
    assert file["checksum_sha256"] is None
    metadata = await authenticated_client.get(f"{API}/files/{file['id']}")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["checksum_sha256"] is None
    download = await authenticated_client.get(f"{API}/files/{file['id']}/download")
    assert download.status_code == 200
    assert download.content == data
    assert attempted == [], (
        "uploads without app.state.background_tasks must not import background_tasks"
    )
