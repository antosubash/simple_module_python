"""Multipart uploads against S3 (moto's HTTP server, real aioboto3) (#454).

Parts are PUT to the presigned URLs exactly as a browser would, so this covers
signing, the ``public`` endpoint override, ``list_parts`` pagination of etags,
completion and the janitor's orphan listing.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from datetime import timedelta

import boto3
import httpx
import pytest
from file_storage import constants
from file_storage.backends import build_backend
from file_storage.contracts.service import Part, StorageNotFoundError
from file_storage.csp import s3_connect_origins
from file_storage.settings import FileStorageSettings
from file_storage_uploads_helpers import API, MIB, open_session
from moto.server import ThreadedMotoServer

_BUCKET = "mp-test-bucket"
_REGION = "us-east-1"
pytestmark = pytest.mark.usefixtures("checksum_calls")
PART = 5 * MIB


@pytest.fixture(scope="module")
def moto_endpoint() -> Generator[str]:
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def s3_settings(moto_endpoint: str) -> FileStorageSettings:
    return FileStorageSettings(
        backend=constants.BackendId.S3,
        s3_bucket=_BUCKET,
        s3_region=_REGION,
        s3_access_key_id="test",
        s3_secret_access_key="test",
        s3_endpoint_url=moto_endpoint,
    )


@pytest.fixture(autouse=True)
def fresh_bucket(moto_endpoint: str):
    client = boto3.client(
        "s3",
        region_name=_REGION,
        endpoint_url=moto_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with contextlib.suppress(client.exceptions.ClientError):
        for obj in client.list_objects_v2(Bucket=_BUCKET).get("Contents", []):
            client.delete_object(Bucket=_BUCKET, Key=obj["Key"])
        client.delete_bucket(Bucket=_BUCKET)
    client.create_bucket(Bucket=_BUCKET)
    yield client


async def _put(url: str, body: bytes) -> str:
    async with httpx.AsyncClient() as http:
        resp = await http.put(url, content=body)
    assert resp.status_code == 200, resp.text
    return resp.headers["ETag"]


async def test_backend_multipart_roundtrip(s3_settings):
    backend = build_backend(s3_settings)
    assert backend.supports_direct_upload is True
    key = "t/2026/10/15/big.bin"
    upload_id = await backend.create_multipart(key, "application/octet-stream")

    body1, body2 = b"a" * PART, b"tail"
    await _put(await backend.presign_part(key, upload_id, 1, 300), body1)
    await _put(await backend.presign_part(key, upload_id, 2, 300), body2)

    parts = await backend.list_parts(key, upload_id)
    assert [(p.no, p.size) for p in parts] == [(1, PART), (2, 4)]
    assert all(isinstance(p, Part) and p.etag for p in parts)

    await backend.complete_multipart(key, upload_id, parts)
    info = await backend.head(key)
    assert info.size == PART + 4
    chunks = [c async for c in await backend.get(key)]
    assert b"".join(chunks) == body1 + body2


async def test_head_of_a_missing_object(s3_settings):
    backend = build_backend(s3_settings)
    with pytest.raises(StorageNotFoundError):
        await backend.head("nope")


async def test_abort_discards_parts_and_is_idempotent(s3_settings):
    backend = build_backend(s3_settings)
    key = "t/abort.bin"
    upload_id = await backend.create_multipart(key, "application/octet-stream")
    await _put(await backend.presign_part(key, upload_id, 1, 300), b"x")

    await backend.abort_multipart(key, upload_id)
    await backend.abort_multipart(key, upload_id)  # NoSuchUpload is not an error
    with pytest.raises(StorageNotFoundError):
        await backend.list_parts(key, upload_id)


async def test_presigned_put_url_stores_a_whole_object(s3_settings):
    backend = build_backend(s3_settings)
    await _put(await backend.presigned_put_url("t/one.txt", 300, "text/plain"), b"hello")
    assert (await backend.head("t/one.txt")).size == 5


async def test_a_part_url_is_bound_to_the_part_length(s3_settings):
    backend = build_backend(s3_settings)
    bound = await backend.presign_part("k", "uid", 1, 300, 1234)
    assert "content-length" in bound.lower().split("x-amz-signedheaders=")[1].split("&")[0]
    unbound = await backend.presign_part("k", "uid", 1, 300)
    assert "content-length" not in unbound.lower().split("x-amz-signedheaders=")[1].split("&")[0]


async def test_public_endpoint_is_what_gets_signed(s3_settings):
    settings = s3_settings.model_copy(
        update={"s3_public_endpoint_url": "https://files.example.test"}
    )
    backend = build_backend(settings)
    url = await backend.presign_part("k", "uid", 1, 300)
    assert url.startswith("https://files.example.test/")
    assert "X-Amz-Signature" in url
    assert (await backend.presigned_get_url("k", 300)).startswith("https://files.example.test/")


async def test_list_stale_multipart_lists_in_progress_uploads(s3_settings):
    # moto hard-codes `Initiated` to 2010, so the age filter itself is covered
    # by the opt-in real-S3 test; here only the listing and pairing are checked.
    backend = build_backend(s3_settings)
    upload_id = await backend.create_multipart("t/stale.bin", "application/octet-stream")

    assert await backend.list_stale_multipart(timedelta(days=1)) == [("t/stale.bin", upload_id)]
    await backend.abort_multipart("t/stale.bin", upload_id)
    assert await backend.list_stale_multipart(timedelta(days=1)) == []


class TestCsp:
    def test_custom_endpoint_contributes_its_origin(self, s3_settings):
        assert s3_connect_origins(s3_settings) == [s3_settings.s3_endpoint_url]

    def test_public_endpoint_wins_and_loses_its_path(self, s3_settings):
        settings = s3_settings.model_copy(
            update={"s3_public_endpoint_url": "https://files.example.test/prefix?x=1"}
        )
        assert s3_connect_origins(settings) == ["https://files.example.test"]

    def test_aws_default_allows_the_bucket_hosts(self):
        settings = FileStorageSettings(
            backend=constants.BackendId.S3, s3_bucket="b", s3_region="eu-west-1"
        )
        assert s3_connect_origins(settings) == [
            "https://b.s3.eu-west-1.amazonaws.com",
            "https://b.s3.amazonaws.com",
        ]

    def test_filesystem_adds_nothing(self):
        assert s3_connect_origins(FileStorageSettings()) == []


async def test_api_flow_uploads_straight_to_the_bucket(
    app, authenticated_client, s3_settings, fresh_bucket
):
    services = app.state.file_storage
    services.backend = build_backend(s3_settings)
    services.settings.multipart_part_size_bytes = PART
    data = b"z" * PART + b"end"

    session = (await open_session(authenticated_client, total=len(data))).json()
    urls = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/part-urls", json={"parts": [1, 2]}
    )
    body = urls.json()
    assert body["direct"] is True
    assert body["urls"]["1"].startswith(s3_settings.s3_endpoint_url)

    etags = {
        1: await _put(body["urls"]["1"], data[:PART]),
        2: await _put(body["urls"]["2"], data[PART:]),
    }
    resumed = (await authenticated_client.get(f"{API}/uploads/{session['id']}")).json()
    assert [p["no"] for p in resumed["parts"]] == [1, 2]

    done = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/complete",
        json={"parts": [{"n": n, "etag": e} for n, e in etags.items()]},
    )
    assert done.status_code == 200, done.text
    file = done.json()["file"]
    assert file["backend"] == constants.BackendId.S3
    assert file["size_bytes"] == len(data)
    assert file["checksum_sha256"] is None
    assert fresh_bucket.head_object(Bucket=_BUCKET, Key=file["key"])["ContentLength"] == len(data)


async def test_api_rejects_an_object_of_the_wrong_size(
    app, authenticated_client, s3_settings, fresh_bucket
):
    """A client that lied about ``total_size`` gets no StoredFile and no orphan object."""
    services = app.state.file_storage
    services.backend = build_backend(s3_settings)
    services.settings.multipart_part_size_bytes = PART

    session = (await open_session(authenticated_client, total=PART + 10)).json()
    urls = (
        await authenticated_client.post(
            f"{API}/uploads/{session['id']}/part-urls", json={"parts": [1, 2]}
        )
    ).json()["urls"]
    etags = {1: await _put(urls["1"], b"a" * PART), 2: await _put(urls["2"], b"b" * 3)}

    resp = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/complete",
        json={"parts": [{"n": n, "etag": e} for n, e in etags.items()]},
    )
    # The part-size check catches the short last part before assembly.
    assert resp.status_code == 409
    assert fresh_bucket.list_objects_v2(Bucket=_BUCKET).get("Contents", []) == []
