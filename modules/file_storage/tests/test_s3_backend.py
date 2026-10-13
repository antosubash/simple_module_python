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
    out = await _drain(await backend.get("2026/04/19/abc.bin"))
    assert out == payload

    await backend.delete("2026/04/19/abc.bin")
    assert await backend.exists("2026/04/19/abc.bin") is False


async def test_s3_get_missing_raises_not_found(s3_settings):
    backend = build_backend(s3_settings)
    # Raised by the awaited call itself, before any response could start.
    with pytest.raises(StorageNotFoundError):
        await backend.get("missing")
    with pytest.raises(StorageNotFoundError):
        await backend.get_range("missing", 0, 9)


_BIG = bytes(range(256)) * 1000  # 256,000 bytes: four 64 KiB reads


async def _put(backend, key: str, data: bytes) -> None:
    await backend.put(
        key, _bytes_stream(data), content_type="application/octet-stream", size=len(data)
    )


@pytest.fixture
def body_reads(monkeypatch) -> list[int | None]:
    """Record the ``amt`` of every ``StreamingBody.read`` (``None`` = read-all)."""
    from aiobotocore.response import StreamingBody

    calls: list[int | None] = []
    real = StreamingBody.read

    async def spy(self, amt=None):
        calls.append(amt)
        return await real(self, amt)

    monkeypatch.setattr(StreamingBody, "read", spy)
    return calls


async def test_s3_get_streams_in_bounded_reads(s3_settings, body_reads):
    # #453: the body used to be read whole before the first byte was sent.
    backend = build_backend(s3_settings)
    await _put(backend, "big.bin", _BIG)
    chunks = [chunk async for chunk in await backend.get("big.bin")]
    assert b"".join(chunks) == _BIG
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= constants.DEFAULT_CHUNK_SIZE
    assert body_reads and None not in body_reads
    assert set(body_reads) == {constants.DEFAULT_CHUNK_SIZE}


async def test_s3_get_range_is_inclusive_and_streamed(s3_settings, body_reads):
    backend = build_backend(s3_settings)
    await _put(backend, "big.bin", _BIG)
    assert await _drain(await backend.get_range("big.bin", 0, 16383)) == _BIG[:16384]
    assert await _drain(await backend.get_range("big.bin", 5, 5)) == _BIG[5:6]
    tail = await _drain(await backend.get_range("big.bin", 100_000, len(_BIG) - 1))
    assert tail == _BIG[100_000:]
    assert None not in body_reads


async def test_s3_closing_stream_early_releases_body(s3_settings, monkeypatch):
    from aiobotocore.response import StreamingBody

    closed: list[bool] = []
    monkeypatch.setattr(StreamingBody, "close", lambda self: closed.append(True), raising=False)
    backend = build_backend(s3_settings)
    await _put(backend, "big.bin", _BIG)
    stream = await backend.get("big.bin")
    first = await anext(aiter(stream))
    assert len(first) <= constants.DEFAULT_CHUNK_SIZE
    await stream.aclose()  # what Starlette does when the client disconnects
    assert closed == [True]


async def test_s3_get_empty_object(s3_settings):
    backend = build_backend(s3_settings)
    await _put(backend, "empty.bin", b"")
    assert await _drain(await backend.get("empty.bin")) == b""


async def test_s3_presigned_url_format(s3_settings):
    backend = build_backend(s3_settings)
    url = await backend.presigned_get_url("any/key.txt", ttl_seconds=300)
    assert url.startswith("http")
    assert "any/key.txt" in url
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "AWSAccessKeyId=" not in url


async def test_s3_signature_version_is_configurable(s3_settings):
    s3_settings.s3_signature_version = "s3"
    backend = build_backend(s3_settings)
    url = await backend.presigned_get_url("any/key.txt", ttl_seconds=300)
    assert "AWSAccessKeyId=" in url


@pytest.mark.parametrize("value", ["s3v5", "", "v4"])
def test_unknown_signature_version_is_rejected_at_config_time(value) -> None:
    # A typo saved in the admin UI must fail validation, not every upload.
    from file_storage.settings import FileStorageSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FileStorageSettings(s3_signature_version=value)
