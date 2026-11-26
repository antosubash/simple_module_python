"""Public HEAD must not presign GETs or render/read thumbnail bodies (#1139, #1140)."""

from __future__ import annotations

import io

import pytest
from botocore.exceptions import ClientError
from file_storage.core import constants
from file_storage.files import thumbnails
from PIL import Image

API = constants.ROUTE_PREFIX_API


async def _upload(client, data=b"hello", ctype="text/plain", name="a.txt"):
    response = await client.post(
        f"{API}/upload", files={"file": (name, data, ctype)}, data={"public": "true"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _png():
    output = io.BytesIO()
    Image.new("RGB", (100, 50)).save(output, "PNG")
    return output.getvalue()


def _unexpected(*args, **kwargs):
    raise AssertionError("HEAD read/decoded/wrote a thumbnail body")


@pytest.fixture
def s3_objects(app, wire_backend, monkeypatch):
    wire, backend = wire_backend
    objects = {}
    backend.multipart_threshold_bytes = 1024 * 1024

    async def put_object(**kwargs):
        objects[kwargs["Key"]] = kwargs["Body"].read()

    async def head_object(**kwargs):
        key = kwargs["Key"]
        if key not in objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(objects[key]), "ETag": '"bucket-etag"'}

    async def presign(operation, **kwargs):
        assert operation == "get_object"
        assert kwargs["Params"]["ResponseContentType"] == "text/plain"
        assert kwargs["Params"]["ResponseContentDisposition"].startswith("inline;")
        return "https://bucket.example/download?signed=get_object"

    monkeypatch.setattr(wire, "put_object", put_object)
    monkeypatch.setattr(wire, "head_object", head_object, raising=False)
    monkeypatch.setattr(wire, "generate_presigned_url", presign, raising=False)
    app.state.file_storage.backend = backend
    return objects


async def test_s3_original_head_answers_metadata_while_get_redirects(
    authenticated_client, client, app, s3_objects, monkeypatch
):
    body = await _upload(authenticated_client)
    backend = app.state.file_storage.backend
    monkeypatch.setattr(backend, "get", _unexpected)
    monkeypatch.setattr(backend, "get_range", _unexpected)
    for url in (f"{API}/public/{body['id']}", body["public_url"]):
        get = await client.get(url, follow_redirects=False)
        assert get.status_code == 302
        assert get.headers["location"] == "https://bucket.example/download?signed=get_object"
        with monkeypatch.context() as patch:
            patch.setattr(backend, "presigned_get_url", _unexpected)
            head = await client.head(url, headers={"Range": "bytes=99-"})
        assert head.status_code == 200
        assert head.content == b""
        assert "location" not in head.headers
        assert "content-range" not in head.headers
        assert head.headers["content-length"] == "5"
        assert head.headers["content-type"] == "text/plain; charset=utf-8"
        assert head.headers["content-disposition"].startswith('inline; filename="a.txt"')
        assert head.headers["etag"] == get.headers["etag"]
        assert "sandbox" in head.headers["content-security-policy"]
        conditional = await client.head(url, headers={"If-None-Match": head.headers["etag"]})
        assert conditional.status_code == 304
    s3_objects.clear()
    assert (await client.head(body["public_url"])).status_code == 404


async def test_cached_thumbnail_head_never_reads_body(
    authenticated_client, client, app, monkeypatch
):
    body = await _upload(authenticated_client, _png(), "image/png", "a.png")
    url = f"{API}/public/{body['id']}/thumbnail?w=100"
    get = await client.get(url, headers={"Accept-Encoding": "identity"})
    assert get.status_code == 200
    backend = app.state.file_storage.backend
    monkeypatch.setattr(backend, "get", _unexpected)
    monkeypatch.setattr(backend, "get_range", _unexpected)
    monkeypatch.setattr(backend, "put", _unexpected)
    monkeypatch.setattr(thumbnails, "render", _unexpected)
    head = await client.head(url, headers={"Range": "bytes=1-2"})
    assert head.status_code == 200
    assert head.content == b""
    for header in ("content-type", "content-length", "etag", "cache-control"):
        assert head.headers[header] == get.headers[header]
    assert "content-range" not in head.headers
    conditional = await client.head(url, headers={"If-None-Match": head.headers["etag"]})
    assert conditional.status_code == 304


async def test_s3_cached_thumbnail_head_uses_object_metadata(
    authenticated_client, client, app, s3_objects, monkeypatch
):
    body = await _upload(authenticated_client, _png(), "image/png", "a.png")
    s3_objects[thumbnails.variant_key(body["key"], 128)] = b"cached variant bytes"
    backend = app.state.file_storage.backend
    monkeypatch.setattr(backend, "get", _unexpected)
    monkeypatch.setattr(backend, "get_range", _unexpected)
    monkeypatch.setattr(backend, "put", _unexpected)
    head = await client.head(f"{API}/public/{body['id']}/thumbnail?w=100")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == "20"
    assert head.headers["content-type"] == "image/webp"
    assert head.headers["etag"] == f'"{body["checksum_sha256"]}-w128"'


async def test_cold_thumbnail_head_probes_without_generating(
    authenticated_client, client, app, monkeypatch
):
    body = await _upload(authenticated_client, _png(), "image/png", "a.png")
    backend = app.state.file_storage.backend
    monkeypatch.setattr(backend, "put", _unexpected)
    monkeypatch.setattr(thumbnails, "render", _unexpected)
    monkeypatch.setattr(Image.Image, "load", _unexpected)
    monkeypatch.setattr(backend, "get", _unexpected)
    url = f"{API}/public/{body['id']}/thumbnail?w=100"
    head = await client.head(url)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-type"] == "image/webp"
    assert "content-length" not in head.headers
    assert head.headers["etag"] == f'"{body["checksum_sha256"]}-w128"'
    assert not await backend.exists(thumbnails.variant_key(body["key"], 128))


@pytest.mark.parametrize(
    "data,ctype,status",
    [
        (b"not png", "image/png", 422),
        (b"not png" * 10000, "image/png", 422),
        (_png(), "image/jpeg", 422),
        (b"x", "text/plain", 404),
        (b"<svg/>", "image/svg+xml", 404),
    ],
    ids=["invalid", "large-invalid", "wrong-format", "text", "svg"],
)
async def test_cold_thumbnail_head_preserves_error_status(
    authenticated_client, client, data, ctype, status
):
    body = await _upload(authenticated_client, data, ctype)
    url = f"{API}/public/{body['id']}/thumbnail"
    assert (await client.get(url)).status_code == status
    head = await client.head(url)
    assert head.status_code == status
    assert head.content == b""


async def test_cold_thumbnail_head_missing_original_is_404(authenticated_client, client, app):
    body = await _upload(authenticated_client, _png(), "image/png", "a.png")
    await app.state.file_storage.backend.delete(body["key"])
    url = f"{API}/public/{body['id']}/thumbnail"
    assert (await client.get(url)).status_code == 404
    assert (await client.head(url)).status_code == 404


@pytest.mark.parametrize("budget", ["THUMBNAIL_MAX_PIXELS", "THUMBNAIL_MAX_SOURCE_BYTES"])
async def test_cold_thumbnail_head_preserves_image_budgets(
    authenticated_client, client, monkeypatch, budget
):
    body = await _upload(authenticated_client, _png(), "image/png", "a.png")
    monkeypatch.setattr(constants, budget, 10)
    url = f"{API}/public/{body['id']}/thumbnail"
    assert (await client.get(url)).status_code == 422
    assert (await client.head(url)).status_code == 422
