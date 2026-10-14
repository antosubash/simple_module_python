"""``Range`` → ``206`` on the download endpoints, filesystem backend (#453)."""

from __future__ import annotations

import httpx
from file_storage import constants

API = constants.ROUTE_PREFIX_API
PAYLOAD = bytes(range(256)) * 800  # 204,800 bytes: several 64 KiB chunks
SIZE = len(PAYLOAD)
DISPOSITION = 'attachment; filename="tiles.pmtiles"'


async def _upload(client: httpx.AsyncClient, **form) -> dict:
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}",
        files={"file": ("tiles.pmtiles", PAYLOAD, "application/octet-stream")},
        data=form,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _download(client: httpx.AsyncClient, **headers: str) -> httpx.Response:
    body = await _upload(client)
    return await client.get(f"{API}/files/{body['id']}/download", headers=headers)


async def test_no_range_is_a_full_200(authenticated_client):
    # identity: GZip would otherwise compress the full body and drop the length.
    resp = await _download(authenticated_client, **{"Accept-Encoding": "identity"})
    assert resp.status_code == 200
    assert resp.content == PAYLOAD
    assert resp.headers["content-length"] == str(SIZE)
    assert resp.headers["accept-ranges"] == "bytes"
    assert "content-range" not in resp.headers
    assert resp.headers["content-disposition"] == DISPOSITION
    assert resp.headers["etag"].startswith('"')


async def test_first_16k_is_a_206_with_exact_bytes(authenticated_client):
    resp = await _download(authenticated_client, Range="bytes=0-16383")
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[:16384]
    assert resp.headers["content-length"] == "16384"
    assert resp.headers["content-range"] == f"bytes 0-16383/{SIZE}"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-disposition"] == DISPOSITION


async def test_range_spanning_chunks(authenticated_client):
    start, end = 65_000, 140_000
    resp = await _download(authenticated_client, Range=f"bytes={start}-{end}")
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[start : end + 1]


async def test_suffix_range(authenticated_client):
    resp = await _download(authenticated_client, Range="bytes=-100")
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[-100:]
    assert resp.headers["content-range"] == f"bytes {SIZE - 100}-{SIZE - 1}/{SIZE}"


async def test_open_ended_range(authenticated_client):
    resp = await _download(authenticated_client, Range="bytes=200000-")
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[200000:]
    assert resp.headers["content-length"] == str(SIZE - 200000)


async def test_end_past_eof_is_clamped(authenticated_client):
    resp = await _download(authenticated_client, Range="bytes=204700-999999999")
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[204700:]
    assert resp.headers["content-range"] == f"bytes 204700-204799/{SIZE}"


async def test_unsatisfiable_range_is_416(authenticated_client):
    resp = await _download(authenticated_client, Range=f"bytes={SIZE}-")
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{SIZE}"
    assert resp.content == b""


async def test_multi_range_and_garbage_fall_back_to_full_200(authenticated_client):
    for header in ("bytes=0-1,5-6", "bytes=9-2", "lines=1-2", "bytes=abc"):
        resp = await _download(authenticated_client, Range=header)
        assert resp.status_code == 200, header
        assert resp.content == PAYLOAD


async def test_stale_if_range_sends_everything(authenticated_client):
    body = await _upload(authenticated_client)
    url = f"{API}/files/{body['id']}/download"
    etag = (await authenticated_client.get(url)).headers["etag"]

    hit = await authenticated_client.get(url, headers={"Range": "bytes=0-9", "If-Range": etag})
    assert hit.status_code == 206
    assert hit.content == PAYLOAD[:10]
    stale = await authenticated_client.get(
        url, headers={"Range": "bytes=0-9", "If-Range": '"other"'}
    )
    assert stale.status_code == 200
    assert stale.content == PAYLOAD


async def test_range_still_requires_auth(authenticated_client, client):
    body = await _upload(authenticated_client)
    resp = await client.get(f"{API}/files/{body['id']}/download", headers={"Range": "bytes=0-9"})
    assert resp.status_code in (401, 302, 403)


async def test_public_route_serves_ranges_with_its_headers(authenticated_client, client):
    body = await _upload(authenticated_client, public="true")
    url = f"{API}/public/{body['id']}"
    resp = await client.get(url, headers={"Range": "bytes=-16384"})
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[-16384:]
    assert resp.headers["cache-control"].startswith("public, max-age=")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]
    assert resp.headers["content-disposition"].startswith("inline")

    bad = await client.get(url, headers={"Range": "bytes=999999-"})
    assert bad.status_code == 416
    assert bad.headers["content-range"] == f"bytes */{SIZE}"


async def test_ranged_download_never_opens_the_full_body(authenticated_client, monkeypatch):
    from file_storage.backends.filesystem import FilesystemBackend

    body = await _upload(authenticated_client)
    opened: list[str] = []
    real_get = FilesystemBackend.get

    async def spy_get(self, key):
        opened.append(key)
        return await real_get(self, key)

    monkeypatch.setattr(FilesystemBackend, "get", spy_get)
    url = f"{API}/files/{body['id']}/download"
    resp = await authenticated_client.get(url, headers={"Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert opened == []
    full = await authenticated_client.get(url, headers={"Accept-Encoding": "identity"})
    assert full.status_code == 200
    assert len(opened) == 1
