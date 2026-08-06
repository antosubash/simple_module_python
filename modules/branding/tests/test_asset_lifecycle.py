"""Replacing or clearing a branding image must not leak the previous file.

Each upload mints a *new* ``file_storage`` id (that is what makes the published
URL content-addressed), so unlike IIASA.GeoWiki — which overwrites one blob at a
fixed key per image type and so has nothing to clean up — this module has to
delete the file it just stopped referencing. Otherwise every logo tweak leaves
another orphan in the store that nothing will ever reference or reap.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from file_storage.models import StoredFile
from file_storage.service import FileStorageService, StoredFileNotFoundError

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeStore:
    """Mints a fresh row per upload and records what got deleted."""

    def __init__(self) -> None:
        self.uploaded: list[uuid.UUID] = []
        self.deleted: list[uuid.UUID] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = self

        async def fake_upload(self: FileStorageService, upload: Any) -> StoredFile:
            row = StoredFile(
                id=uuid.uuid4(),
                key=f"2026/06/{uuid.uuid4()}.png",
                filename="logo.png",
                content_type="image/png",
                size_bytes=len(_PNG),
                backend="local",
                checksum_sha256="a" * 64,
            )
            store.uploaded.append(row.id)
            return row

        async def fake_delete(self: FileStorageService, file_id: uuid.UUID) -> StoredFile:
            if file_id in store.deleted:
                raise StoredFileNotFoundError(str(file_id))
            store.deleted.append(file_id)
            return StoredFile(
                id=file_id,
                key="k",
                filename="logo.png",
                content_type="image/png",
                size_bytes=0,
                backend="local",
                checksum_sha256="a" * 64,
            )

        monkeypatch.setattr(FileStorageService, "upload", fake_upload, raising=True)
        monkeypatch.setattr(FileStorageService, "delete", fake_delete, raising=True)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    fake = FakeStore()
    fake.install(monkeypatch)
    return fake


async def _upload(client: httpx.AsyncClient, kind: str) -> None:
    resp = await client.post(
        f"/api/branding/{kind}",
        files={"file": (f"{kind}.png", _PNG, "image/png")},
    )
    assert resp.status_code == 200, resp.text


async def test_replacing_a_logo_deletes_the_previous_file(
    store: FakeStore, authenticated_client: httpx.AsyncClient
) -> None:
    await _upload(authenticated_client, "logo")
    await _upload(authenticated_client, "logo")

    first, second = store.uploaded
    assert store.deleted == [first], "the replaced logo was left orphaned in file_storage"
    assert second not in store.deleted, "the logo now in use must survive"


async def test_clearing_a_logo_deletes_the_file(
    store: FakeStore, authenticated_client: httpx.AsyncClient
) -> None:
    await _upload(authenticated_client, "logo")

    resp = await authenticated_client.delete("/api/branding/logo")

    assert resp.status_code == 200, resp.text
    assert store.deleted == store.uploaded


async def test_clearing_twice_is_harmless(
    store: FakeStore, authenticated_client: httpx.AsyncClient
) -> None:
    # Nothing referenced any more, so the second clear has nothing to delete.
    await _upload(authenticated_client, "logo")
    await authenticated_client.delete("/api/branding/logo")

    resp = await authenticated_client.delete("/api/branding/logo")

    assert resp.status_code == 200, resp.text
    assert len(store.deleted) == 1


async def test_logo_and_favicon_are_reaped_independently(
    store: FakeStore, authenticated_client: httpx.AsyncClient
) -> None:
    await _upload(authenticated_client, "logo")
    await _upload(authenticated_client, "favicon")

    await authenticated_client.delete("/api/branding/logo")

    logo_id, favicon_id = store.uploaded
    assert store.deleted == [logo_id]
    assert favicon_id not in store.deleted


async def test_a_failed_cleanup_does_not_fail_the_rebrand(
    store: FakeStore, authenticated_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The setting change already succeeded and is what the admin asked for. A
    # storage blip while reaping the old file must not surface as a 500 on an
    # otherwise-successful rebrand.
    #
    # Covers a fault raised before any DB write — which is every realistic case
    # (missing row, bad UUID, backend error). A failure *during* flush is out of
    # reach by design; see BrandingService._reap.
    await _upload(authenticated_client, "logo")

    async def boom(self: FileStorageService, file_id: uuid.UUID) -> StoredFile:
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(FileStorageService, "delete", boom, raising=True)

    resp = await authenticated_client.delete("/api/branding/logo")

    assert resp.status_code == 200, resp.text
    assert resp.json()["logo_url"] is None
