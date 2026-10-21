"""Cross-origin reads of public files (#527)."""

from __future__ import annotations

from file_storage import constants

API = constants.ROUTE_PREFIX_API
ORIGIN = "https://site.example.org"
PAYLOAD = bytes(range(256)) * 4


async def _public_file(authenticated_client) -> str:
    resp = await authenticated_client.post(
        f"{API}{constants.PATH_UPLOAD}",
        files={"file": ("a.bin", PAYLOAD, "application/octet-stream")},
        data={"public": "true"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["public_url"]


async def test_cross_origin_range_get_is_206_and_exposes_headers(authenticated_client, client):
    url = await _public_file(authenticated_client)
    resp = await client.get(url, headers={"Origin": ORIGIN, "Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in resp.headers
    assert "content-range" in resp.headers["access-control-expose-headers"].lower()


async def test_preflight_allows_range(authenticated_client, client):
    url = await _public_file(authenticated_client)
    resp = await client.options(
        url,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "range",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"


async def test_setting_off_removes_cors_headers(app, authenticated_client, client):
    url = await _public_file(authenticated_client)
    app.state.file_storage.settings.public_files_cors = False
    resp = await client.get(url, headers={"Origin": ORIGIN, "Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert "access-control-allow-origin" not in resp.headers
    assert "access-control-expose-headers" not in resp.headers
