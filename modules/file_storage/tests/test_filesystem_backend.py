"""Tests for the filesystem storage backend."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.contracts.service import (
    NotSupportedError,
    StorageBackendError,
    StorageNotFoundError,
)


async def _bytes_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def test_put_then_get_roundtrip(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    payload = b"hello world"
    await backend.put(
        "ab/file1.bin", _bytes_stream(payload), content_type="text/plain", size=len(payload)
    )

    body = await backend.get("ab/file1.bin")
    out = b""
    async for chunk in body:
        out += chunk
    assert out == payload


async def test_exists_and_delete(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    await backend.put("aa/x", _bytes_stream(b"x"), content_type="text/plain", size=1)

    assert await backend.exists("aa/x") is True
    await backend.delete("aa/x")
    assert await backend.exists("aa/x") is False


async def test_get_missing_raises_not_found(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    with pytest.raises(StorageNotFoundError):
        await backend.get("missing/key")


async def test_path_traversal_rejected(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    with pytest.raises(StorageBackendError):
        await backend.put("../escape", _bytes_stream(b"x"), content_type="text/plain", size=1)
    with pytest.raises(StorageBackendError):
        await backend.put("/etc/passwd", _bytes_stream(b"x"), content_type="text/plain", size=1)


async def test_presigned_url_not_supported(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    with pytest.raises(NotSupportedError):
        await backend.presigned_get_url("any", 60)


async def test_two_char_shard_layout(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    await backend.put("ab/file.bin", _bytes_stream(b"x"), content_type="text/plain", size=1)
    # Stored at <root>/ab/ab/file.bin (2-char shard prefix from key[:2])
    assert (tmp_path / "ab" / "ab" / "file.bin").exists()


async def _drain(stream: AsyncIterator[bytes]) -> list[bytes]:
    return [chunk async for chunk in stream]


async def test_get_range_is_inclusive_and_chunked(tmp_path):
    from file_storage import constants

    backend = FilesystemBackend(root=tmp_path)
    data = bytes(range(256)) * 1000
    await backend.put("ab/big", _bytes_stream(data), content_type="x/y", size=len(data))

    assert b"".join(await _drain(await backend.get_range("ab/big", 0, 16383))) == data[:16384]
    assert b"".join(await _drain(await backend.get_range("ab/big", 7, 7))) == data[7:8]
    chunks = await _drain(await backend.get_range("ab/big", 1000, 200_000))
    assert b"".join(chunks) == data[1000:200_001]
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= constants.DEFAULT_CHUNK_SIZE


async def test_get_range_missing_raises_not_found(tmp_path):
    backend = FilesystemBackend(root=tmp_path)
    with pytest.raises(StorageNotFoundError):
        await backend.get_range("missing/key", 0, 1)
