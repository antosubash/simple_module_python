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
