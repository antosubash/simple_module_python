"""Bounded cold-source probes and compatibility with older storage providers."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.files import thumbnail_metadata, thumbnails
from PIL import Image


def _image(format):
    output = io.BytesIO()
    Image.new("RGB", (40, 20)).save(output, format)
    return output.getvalue()


@pytest.mark.parametrize(
    "format,ctype",
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("GIF", "image/gif"), ("WEBP", "image/webp")],
)
async def test_cold_probe_reads_only_a_prefix_and_closes_stream(format, ctype, monkeypatch):
    data = _image(format)
    if format == "JPEG":
        # Two legal APP2 segments put the dimensions beyond the probe budget.
        metadata = (b"\xff\xe2\xff\xff" + b"x" * 65533) * 2
        data = data[:2] + metadata + data[2:]
    data += b"padding" * 20000
    closed = []
    reads = []

    async def exists(key):
        return key == "source"

    async def get_range(key, start, end):
        reads.append((key, start, end))

        async def stream():
            try:
                yield data[start : end + 1]
            finally:
                closed.append(True)

        return stream()

    def unexpected_load(*args, **kwargs):
        raise AssertionError("HEAD decoded pixels")

    monkeypatch.setattr(Image.Image, "load", unexpected_load)
    backend = SimpleNamespace(exists=exists, get_range=get_range)
    size = await thumbnail_metadata.head_size(
        backend, key="source", content_type=ctype, width=128, source_size=len(data)
    )
    assert size is None
    assert reads == [("source", 0, 65535)]
    assert closed == [True]


async def test_cached_probe_without_metadata_support_does_not_read_body(tmp_path):
    backend = FilesystemBackend(tmp_path)

    async def chunks():
        yield b"cached thumbnail"

    await backend.put(
        thumbnails.variant_key("source", 128), chunks(), content_type="image/webp", size=16
    )
    legacy = SimpleNamespace(exists=backend.exists)
    assert (
        await thumbnail_metadata.head_size(
            legacy, key="source", content_type="image/png", width=128, source_size=100
        )
        is None
    )


async def test_cold_probe_without_range_support_closes_stream():
    closed = []

    async def exists(key):
        return key == "source"

    async def get(key):
        assert key == "source"

        async def stream():
            try:
                yield _image("PNG") + b"padding" * 20000
                raise AssertionError("HEAD kept reading past its probe budget")
            finally:
                closed.append(True)

        return stream()

    legacy = SimpleNamespace(exists=exists, get=get)
    assert (
        await thumbnail_metadata.head_size(
            legacy, key="source", content_type="image/png", width=128, source_size=140000
        )
        is None
    )
    assert closed == [True]
