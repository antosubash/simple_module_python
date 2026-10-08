"""Anonymous serving of ``public`` files (#353)."""

from __future__ import annotations

import uuid

import httpx
from file_storage import constants

API = constants.ROUTE_PREFIX_API


async def _upload(client, name="a.txt", data=b"hello", ctype="text/plain", **form):
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}", files={"file": (name, data, ctype)}, data=form
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_upload_private_by_default_has_no_public_url(authenticated_client):
    body = await _upload(authenticated_client)
    assert body["public"] is False
    assert body["public_url"] is None


async def test_upload_public_returns_url_and_anonymous_get_works(
    authenticated_client, client: httpx.AsyncClient
):
    body = await _upload(authenticated_client, public="true")
    assert body["public"] is True
    assert body["public_url"] == f"{API}/public/{body['id']}/a.txt"

    for url in (f"{API}/public/{body['id']}", body["public_url"]):
        resp = await client.get(url)
        assert resp.status_code == 200, resp.text
        assert resp.content == b"hello"
        assert resp.headers["cache-control"].startswith("public, max-age=")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in resp.headers["content-security-policy"]
        assert resp.headers["content-disposition"].startswith("inline")
        etag = resp.headers["etag"]
    again = await client.get(f"{API}/public/{body['id']}", headers={"If-None-Match": etag})
    assert again.status_code == 304


async def test_private_file_is_404_anonymously(authenticated_client, client):
    body = await _upload(authenticated_client)
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 404
    assert (await client.get(f"{API}/public/{uuid.uuid4()}")).status_code == 404


async def test_patch_toggles_public(authenticated_client, client):
    body = await _upload(authenticated_client)
    url = f"{API}/files/{body['id']}"
    resp = await authenticated_client.patch(url, json={"public": True})
    assert resp.status_code == 200
    assert resp.json()["public_url"]
    assert (await authenticated_client.get(url)).json()["public"] is True
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 200

    resp = await authenticated_client.patch(url, json={"public": False})
    assert resp.json()["public"] is False
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 404


async def test_patch_requires_auth_and_known_id(authenticated_client, client):
    assert (
        await authenticated_client.patch(f"{API}/files/{uuid.uuid4()}", json={"public": True})
    ).status_code == 404
    body = await _upload(authenticated_client)
    anon = await client.patch(f"{API}/files/{body['id']}", json={"public": True})
    assert anon.status_code in (401, 302, 403)


async def test_deleted_public_file_is_404(authenticated_client, client):
    body = await _upload(authenticated_client, public="true")
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 200
    assert (await authenticated_client.delete(f"{API}/files/{body['id']}")).status_code == 204
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 404


async def test_active_content_is_attachment_and_sandboxed(authenticated_client, client):
    body = await _upload(
        authenticated_client,
        name="x.svg",
        data=b"<svg onload=alert(1)/>",
        ctype="image/svg+xml",
        public="true",
    )
    resp = await client.get(f"{API}/public/{body['id']}")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in resp.headers["content-security-policy"]


async def test_public_write_routes_stay_gated(client):
    body = {"file": ("a.txt", b"x", "text/plain")}
    resp = await client.post(f"{API}{constants.PATH_UPLOAD}", files=body)
    assert resp.status_code in (401, 302, 403)
    resp = await client.get(f"{API}/files")
    assert resp.status_code in (401, 302, 403)


async def test_cross_tenant_public_file_served_but_private_not(app, client):
    """Anonymous callers bind no tenant: a public file of any tenant resolves
    by id (it is public by its owner's choice); a private one never does."""
    from file_storage.models import StoredFile
    from simple_module_db import tenant_context

    ids = {}
    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            for name, public in (("pub", True), ("priv", False)):
                row = StoredFile(
                    key=f"acme/{name}",
                    filename=f"{name}.txt",
                    content_type="text/plain",
                    size_bytes=1,
                    backend=constants.BackendId.FILESYSTEM,
                    checksum_sha256="0" * 64,
                    public=public,
                )
                session.add(row)
                await session.flush()
                ids[name] = row.id
        await session.commit()
    services = app.state.file_storage

    async def _gen():
        yield b"x"

    await services.backend.put("acme/pub", _gen(), content_type="text/plain", size=1)
    assert (await client.get(f"{API}/public/{ids['pub']}")).status_code == 200
    assert (await client.get(f"{API}/public/{ids['priv']}")).status_code == 404


async def test_patch_public_rejects_non_boolean(authenticated_client, client):
    body = await _upload(authenticated_client)
    url = f"{API}/files/{body['id']}"
    for value in ("yes", "true", 1, 0, None):
        resp = await authenticated_client.patch(url, json={"public": value})
        assert resp.status_code == 422, (value, resp.text)
    assert (await authenticated_client.get(url)).json()["public"] is False
    assert (await client.get(f"{API}/public/{body['id']}")).status_code == 404
