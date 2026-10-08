"""Thumbnail variants are dropped even when deleting the original fails."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import UploadFile
from file_storage import constants, thumbnails
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings


class BrokenOriginals(FilesystemBackend):
    """Deleting an original fails; deleting a variant works."""

    async def delete(self, key: str) -> None:
        if not key.endswith(".webp"):
            raise OSError("backend is on fire")
        await super().delete(key)


async def _service_with_variant(tmp_path, db_session):
    settings = FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM, fs_root_path=str(tmp_path)
    )
    backend = BrokenOriginals(root=tmp_path)
    svc = FileStorageService(db_session, backend, settings)
    upload = UploadFile(
        filename="p.png",
        file=BytesIO(b"x"),
        headers={"content-type": "image/png"},  # type: ignore[arg-type]
    )
    out = await svc.upload(upload)
    variant = thumbnails.variant_key(out.key, 128)

    async def _once():
        yield b"v"

    await backend.put(variant, _once(), content_type="image/webp", size=1)
    assert await backend.exists(variant)
    return svc, out, variant


async def test_delete_drops_variants_when_original_delete_raises(tmp_path, db_session):
    svc, out, variant = await _service_with_variant(tmp_path, db_session)
    # The error still reaches the caller, unchanged.
    with pytest.raises(OSError, match="on fire"):
        await svc.delete(out.id)
    assert not await svc.backend.exists(variant)


async def test_bulk_delete_drops_variants_when_original_delete_raises(tmp_path, db_session):
    svc, out, variant = await _service_with_variant(tmp_path, db_session)
    removed = await svc.delete_many([out.id])
    assert [r.id for r in removed] == [out.id]
    assert not await svc.backend.exists(variant)
