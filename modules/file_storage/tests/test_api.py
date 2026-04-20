"""End-to-end tests for the file_storage REST API via authenticated_client."""

from __future__ import annotations

import httpx
from file_storage import constants


async def test_upload_then_list(authenticated_client: httpx.AsyncClient):
    files = {"file": ("hello.txt", b"hi", "text/plain")}
    resp = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files=files,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] == "hello.txt"
    assert body["content_type"] == "text/plain"
    assert body["backend"] == constants.BackendId.FILESYSTEM
    assert body["size_bytes"] == 2

    list_resp = await authenticated_client.get(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}"
    )
    assert list_resp.status_code == 200
    listing = list_resp.json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == body["id"]


async def test_download_streams_filesystem_bytes(authenticated_client: httpx.AsyncClient):
    payload = b"streamed content"
    files = {"file": ("doc.bin", payload, "application/octet-stream")}
    upload = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files=files,
    )
    file_id = upload.json()["id"]

    resp = await authenticated_client.get(f"{constants.ROUTE_PREFIX_API}/files/{file_id}/download")
    assert resp.status_code == 200
    assert resp.content == payload
    assert "attachment" in resp.headers.get("content-disposition", "")


async def test_delete_removes_file(authenticated_client: httpx.AsyncClient):
    upload = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": ("gone.txt", b"x", "text/plain")},
    )
    file_id = upload.json()["id"]

    delete = await authenticated_client.delete(f"{constants.ROUTE_PREFIX_API}/files/{file_id}")
    assert delete.status_code == 204

    fetch = await authenticated_client.get(f"{constants.ROUTE_PREFIX_API}/files/{file_id}")
    assert fetch.status_code == 404


async def test_get_unknown_id_returns_404(authenticated_client: httpx.AsyncClient):
    import uuid

    resp = await authenticated_client.get(f"{constants.ROUTE_PREFIX_API}/files/{uuid.uuid4()}")
    # Framework converts 4xx/5xx HTTPException into an Inertia error page;
    # status code is preserved but the body is HTML.
    assert resp.status_code == 404
