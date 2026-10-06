"""Anonymous public responses are shareable: no session cookie, no ``Vary: Cookie``.

A response marked ``Cache-Control: public`` that also carries ``Set-Cookie``
lets a shared cache store one visitor's session and replay it to the next, and
``Vary: Cookie`` splits the cache per visitor for content that does not depend
on who asked.
"""

from __future__ import annotations

import io

import httpx
from file_storage import constants
from PIL import Image

API = constants.ROUTE_PREFIX_API


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 10, 10)).save(out, format="PNG")
    return out.getvalue()


async def _upload_public(client) -> dict:
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}",
        files={"file": ("p.png", _png(), "image/png")},
        data={"public": "true"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_shareable(resp: httpx.Response) -> None:
    assert "set-cookie" not in resp.headers, resp.headers.get("set-cookie")
    vary = [v.strip().lower() for v in resp.headers.get("vary", "").split(",")]
    assert "cookie" not in vary, resp.headers.get("vary")


def _jar(client: httpx.AsyncClient) -> list[tuple[str, str | None, str]]:
    return sorted((c.name, c.value, c.domain) for c in client.cookies.jar)


async def test_file_storage_public_responses_set_no_cookie(authenticated_client, client):
    body = await _upload_public(authenticated_client)
    urls = (
        f"{API}/public/{body['id']}",
        body["public_url"],
        f"{API}/public/{body['id']}/thumbnail?w=64",
    )
    for url in urls:
        resp = await client.get(url)
        assert resp.status_code == 200, (url, resp.text)
        assert resp.headers["cache-control"].startswith("public, max-age=")
        _assert_shareable(resp)
        again = await client.get(url, headers={"If-None-Match": resp.headers["etag"]})
        assert again.status_code == 304
        _assert_shareable(again)
    assert not client.cookies


async def test_file_storage_public_miss_sets_no_cookie(client):
    resp = await client.get(f"{API}/public/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    _assert_shareable(resp)


async def test_file_storage_signed_in_session_survives_public_fetch(authenticated_client):
    """A signed-in visitor fetching a public file keeps their session intact."""
    body = await _upload_public(authenticated_client)
    before = _jar(authenticated_client)
    resp = await authenticated_client.get(f"{API}/public/{body['id']}")
    assert resp.status_code == 200
    assert "set-cookie" not in resp.headers
    assert _jar(authenticated_client) == before
    # And the session still authenticates afterwards.
    assert (await authenticated_client.get(f"{API}/files")).status_code == 200


async def test_file_storage_other_routes_keep_session_behaviour(client):
    """Only the public file reads are cookieless; an anonymous page still writes it."""
    resp = await client.get("/users/login")
    assert resp.status_code == 200
    assert resp.headers.get("set-cookie", "").startswith("session=")
