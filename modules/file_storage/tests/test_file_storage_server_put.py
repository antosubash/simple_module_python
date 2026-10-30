"""Server-side multipart boundaries without a network service (#708)."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from file_storage import constants
from file_storage.backends import build_backend
from file_storage.settings import FileStorageSettings
from file_storage.upload_support import SizeMismatchError


class S3Wire:
    def __init__(self):
        self.parts = []
        self.single = None
        self.completed = None
        self.aborted = False
        self.failure = None
        self.abort_failure = False

    async def put_object(self, **kw):
        self.single = kw["Body"].read()
        assert kw["ContentLength"] == len(self.single)

    async def create_multipart_upload(self, **kw):
        return {"UploadId": "upload"}

    async def upload_part(self, **kw):
        assert kw["PartNumber"] == len(self.parts) + 1
        body = kw["Body"]
        self.parts.append(body if isinstance(body, bytes) else body.read())
        return {"ETag": str(kw["PartNumber"])}

    async def complete_multipart_upload(self, **kw):
        if self.failure:
            raise self.failure
        self.completed = kw["MultipartUpload"]["Parts"]

    async def abort_multipart_upload(self, **kw):
        self.aborted = True
        if self.abort_failure:
            raise RuntimeError("abort failed")


@pytest.fixture
def wire_backend(monkeypatch):
    wire = S3Wire()
    cfg = FileStorageSettings(
        backend="s3",
        s3_bucket="bucket",
        s3_region="us-east-1",
        direct_upload_threshold_bytes=6,
    )
    backend = build_backend(cfg)

    @asynccontextmanager
    async def client():
        yield wire

    monkeypatch.setattr(backend, "_client", client)
    # Tiny, hand-verifiable parts after testing settings propagation separately.
    backend.multipart_part_size_bytes = 5
    monkeypatch.setattr(
        "file_storage.upload_support.choose_part_size", lambda size, preferred: preferred
    )
    return wire, backend


async def chunks(*values):
    for value in values:
        yield value


@pytest.mark.parametrize(
    "payload,multipart",
    [(b"", False), (b"123456", False), (b"1234567", True), (b"1234567890", True)],
)
@pytest.mark.parametrize("known", [False, True])
async def test_threshold_and_exact_final_part(wire_backend, payload, multipart, known):
    wire, backend = wire_backend
    await backend.put(
        "key",
        chunks(payload[:3], payload[3:]),
        content_type="text/plain",
        size=len(payload) if known else 0,
    )
    if multipart:
        assert b"".join(wire.parts) == payload
        assert [len(p) for p in wire.parts] == ([5, 2] if len(payload) == 7 else [5, 5])
        assert wire.single is None
        assert wire.completed == [{"PartNumber": 1, "ETag": "1"}, {"PartNumber": 2, "ETag": "2"}]
    else:
        assert wire.single == payload
        assert wire.parts == []


@pytest.mark.parametrize("failure", [ValueError("source failed"), asyncio.CancelledError()])
async def test_stream_failure_aborts_and_preserves_error(wire_backend, failure):
    wire, backend = wire_backend
    wire.abort_failure = True

    async def broken():
        yield b"1234567"
        raise failure

    with pytest.raises(type(failure)) as caught:
        await backend.put("key", broken(), content_type="text/plain", size=0)
    assert caught.value is failure
    assert wire.aborted
    assert wire.completed is None


async def test_completion_failure_aborts(wire_backend):
    wire, backend = wire_backend
    wire.failure = RuntimeError("complete failed")
    wire.abort_failure = True
    with pytest.raises(Exception, match="complete failed"):
        await backend.put("key", chunks(b"1234567"), content_type="text/plain", size=0)
    assert wire.aborted


@pytest.mark.parametrize("declared", [2, 8, 12])
async def test_declared_size_mismatch_is_not_published(wire_backend, declared):
    wire, backend = wire_backend
    with pytest.raises(SizeMismatchError):
        await backend.put("key", chunks(b"1234567890"), content_type="text/plain", size=declared)
    assert wire.single is None and wire.completed is None


async def test_part_count_bound_aborts(wire_backend, monkeypatch):
    wire, backend = wire_backend
    monkeypatch.setattr(constants, "MAX_UPLOAD_PARTS", 1)
    with pytest.raises(Exception, match="part"):
        await backend.put("key", chunks(b"12345678901"), content_type="text/plain", size=0)
    assert wire.aborted
    assert len(wire.parts) == 1


def test_factory_passes_stored_multipart_settings():
    backend = build_backend(
        FileStorageSettings(
            backend="s3",
            s3_bucket="bucket",
            s3_region="us-east-1",
            direct_upload_threshold_bytes=123,
            multipart_part_size_bytes=7 * constants.MIB,
        )
    )
    assert backend.multipart_threshold_bytes == 123
    assert backend.multipart_part_size_bytes == 7 * constants.MIB


async def test_unknown_stream_uploads_before_source_is_exhausted(wire_backend):
    wire, backend = wire_backend

    async def source():
        yield b"1234567"
        assert wire.parts == [b"12345"]
        yield b"890"

    await backend.put("key", source(), content_type="text/plain", size=0)
    assert b"".join(wire.parts) == b"1234567890"


async def test_large_source_chunk_keeps_spools_bounded(wire_backend, monkeypatch):
    from tempfile import SpooledTemporaryFile

    from file_storage.backends import s3_put

    maximums = []

    class TrackedBuffer:
        def __init__(self, **kwargs):
            self.file = SpooledTemporaryFile(**kwargs)  # noqa: SIM115 — closed by wrapper context
            self.index = len(maximums)
            maximums.append(0)

        def __getattr__(self, name):
            return getattr(self.file, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, data):
            self.file.write(data)
            maximums[self.index] = max(maximums[self.index], self.file.tell())

    monkeypatch.setattr(s3_put, "SpooledTemporaryFile", TrackedBuffer)
    wire, backend = wire_backend
    await backend.put("key", chunks(b"x" * 100), content_type="text/plain", size=0)
    assert b"".join(wire.parts) == b"x" * 100
    assert maximums == [7, 5]


async def test_failed_part_upload_aborts(wire_backend, monkeypatch):
    wire, backend = wire_backend

    async def fail(**kwargs):
        raise RuntimeError("part failed")

    monkeypatch.setattr(wire, "upload_part", fail)
    with pytest.raises(Exception, match="part failed"):
        await backend.put("key", chunks(b"1234567"), content_type="text/plain", size=0)
    assert wire.aborted and wire.completed is None
