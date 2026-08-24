"""S3 backend tests against a real ``moto.server.ThreadedMotoServer``.

We intentionally avoid the in-process ``@mock_aws`` decorator: it patches
``botocore`` but leaves ``aiobotocore``'s response handling tripping on
"object bytes can't be used in 'await' expression" for ``Body.read``. Running
moto as an HTTP server and pointing the S3 backend at it via
``s3_endpoint_url`` exercises the real aioboto3 client end-to-end.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Generator

import boto3
import pytest
from file_storage import constants
from file_storage.backends import build_backend
from file_storage.contracts.service import StorageNotFoundError
from file_storage.settings import FileStorageSettings
from moto.server import ThreadedMotoServer

_BUCKET = "test-bucket"
_REGION = "us-east-1"


@pytest.fixture(scope="module")
def moto_endpoint() -> Generator[str, None, None]:
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
def reset_bucket(moto_endpoint: str):
    """Recreate the bucket fresh per test (moto persists across tests in server mode)."""
    client = boto3.client(
        "s3",
        region_name=_REGION,
        endpoint_url=moto_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with contextlib.suppress(client.exceptions.ClientError):
        client.delete_bucket(Bucket=_BUCKET)
    client.create_bucket(Bucket=_BUCKET)
    yield


async def _bytes_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def _drain(stream: AsyncIterator[bytes]) -> bytes:
    out = b""
    async for chunk in stream:
        out += chunk
    return out


async def test_s3_put_get_delete_roundtrip(s3_settings):
    backend = build_backend(s3_settings)
    payload = b"contents"
    await backend.put(
        "2026/04/19/abc.bin",
        _bytes_stream(payload),
        content_type="application/octet-stream",
        size=len(payload),
    )
    assert await backend.exists("2026/04/19/abc.bin") is True
    out = await _drain(backend.get("2026/04/19/abc.bin"))
    assert out == payload

    await backend.delete("2026/04/19/abc.bin")
    assert await backend.exists("2026/04/19/abc.bin") is False


async def test_s3_get_missing_raises_not_found(s3_settings):
    backend = build_backend(s3_settings)
    with pytest.raises(StorageNotFoundError):
        await _drain(backend.get("missing"))


async def test_s3_presigned_url_format(s3_settings):
    backend = build_backend(s3_settings)
    url = await backend.presigned_get_url("any/key.txt", ttl_seconds=300)
    assert url.startswith("http")
    assert "any/key.txt" in url
    assert "X-Amz-Signature" in url or "Signature" in url


async def test_s3_roundtrip_under_a_folder_prefix(s3_settings, moto_endpoint):
    """Prefixed keys are ordinary keys to the backend — it never prepends."""
    key = "media/2026/04/19/abc.bin"
    backend = build_backend(s3_settings)
    payload = b"prefixed contents"
    await backend.put(
        key,
        _bytes_stream(payload),
        content_type="application/octet-stream",
        size=len(payload),
    )

    assert await backend.exists(key) is True
    assert await _drain(backend.get(key)) == payload

    # The object really lives under the folder in the bucket.
    listing = boto3.client(
        "s3",
        region_name=_REGION,
        endpoint_url=moto_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).list_objects_v2(Bucket=_BUCKET, Prefix="media/")
    assert [obj["Key"] for obj in listing["Contents"]] == [key]

    await backend.delete(key)
    assert await backend.exists(key) is False


async def test_s3_path_addressing_still_reaches_the_bucket(s3_settings):
    """Path-style is what MinIO/Ceph need; prove it round-trips, not just that
    the Config object was built."""
    settings = s3_settings.model_copy(update={"s3_addressing_style": "path"})
    backend = build_backend(settings)
    payload = b"path style"
    await backend.put(
        "p/one.bin", _bytes_stream(payload), content_type="application/octet-stream", size=10
    )
    assert await _drain(backend.get("p/one.bin")) == payload


async def test_s3_presigned_url_points_at_the_public_endpoint(s3_settings):
    settings = s3_settings.model_copy(
        update={"s3_public_endpoint_url": "https://files.example.com"}
    )
    url = await build_backend(settings).presigned_get_url("media/a.txt", ttl_seconds=300)
    assert url.startswith("https://files.example.com")
    assert "media/a.txt" in url
