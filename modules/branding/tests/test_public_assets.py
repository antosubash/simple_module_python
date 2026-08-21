"""Branding's logo + favicon must load for a *logged-out* visitor.

Both are rendered on guest surfaces — ``AuthCardShell`` (sign-in / register),
``PublicLayout`` (the marketing page) and the ``<link rel="icon">`` emitted by
``BrandingHead`` on every page. A white-label deployment is judged on exactly
those screens, so the URL branding publishes has to be anonymously fetchable.

``file_storage``'s own download route is gated by ``file-storage.download``,
which no anonymous request carries, so branding serves its two assets itself.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from file_storage.models import StoredFile
from file_storage.service import FileStorageService, StreamDownload

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def stored_logo(monkeypatch: pytest.MonkeyPatch) -> StoredFile:
    """Stub file_storage so upload + download work without a real backend."""
    row = StoredFile(
        id=uuid.uuid4(),
        key="2026/06/logo.png",
        filename="logo.png",
        content_type="image/png",
        size_bytes=len(_PNG),
        backend="local",
        checksum_sha256="a" * 64,
    )

    async def fake_upload(self: FileStorageService, upload: Any) -> StoredFile:
        return row

    async def fake_download(self: FileStorageService, file_id: uuid.UUID) -> StreamDownload:
        assert file_id == row.id, f"asked for {file_id}, only {row.id} is stored"

        async def body() -> AsyncIterator[bytes]:
            yield _PNG

        return StreamDownload(file=row, body=body())

    monkeypatch.setattr(FileStorageService, "upload", fake_upload, raising=True)
    monkeypatch.setattr(FileStorageService, "download", fake_download, raising=True)
    return row


async def _upload_logo(authenticated_client: httpx.AsyncClient) -> str:
    resp = await authenticated_client.post(
        "/api/branding/logo",
        files={"file": ("logo.png", _PNG, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    url = resp.json()["logo_url"]
    assert url is not None
    return url


async def test_logo_url_is_fetchable_by_a_logged_out_visitor(
    stored_logo: StoredFile,
    authenticated_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
) -> None:
    # The sign-in page renders this exact URL in an <img>. If it 401s the
    # deployment shows a broken image on the one screen every user starts on.
    url = await _upload_logo(authenticated_client)

    resp = await client.get(url, follow_redirects=False)

    assert resp.status_code == 200, f"guest got {resp.status_code} for {url}"
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == _PNG


async def test_the_published_url_is_versioned_by_the_stored_file_id(
    stored_logo: StoredFile,
    authenticated_client: httpx.AsyncClient,
) -> None:
    # Replacing the logo stores a new file, so the id doubles as a
    # content-address: the URL changes and caches invalidate without a purge.
    assert await _upload_logo(authenticated_client) == f"/api/branding/logo?v={stored_logo.id}"


# ── The anonymous exemption is GET-only ────────────────────────────────


async def test_uploading_a_logo_still_requires_authentication(
    client: httpx.AsyncClient,
) -> None:
    # The public-route rule is exact + GET, so it must not open the sibling
    # POST on the same path to the world.
    resp = await client.post("/api/branding/logo", files={"file": ("l.png", _PNG, "image/png")})
    assert resp.status_code in (401, 403)


async def test_clearing_a_logo_still_requires_authentication(client: httpx.AsyncClient) -> None:
    resp = await client.delete("/api/branding/logo")
    assert resp.status_code in (401, 403)


# ── Cache policy ───────────────────────────────────────────────────────


async def test_a_versioned_request_is_cached_for_a_year_and_immutable(
    stored_logo: StoredFile,
    authenticated_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
) -> None:
    url = await _upload_logo(authenticated_client)

    cache_control = (await client.get(url)).headers["cache-control"]

    assert "public" in cache_control
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control


@pytest.mark.parametrize("query", ["", "?v="])
async def test_a_request_without_a_usable_version_is_not_immutable(
    query: str,
    stored_logo: StoredFile,
    authenticated_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
) -> None:
    # That URL is stable, so the same address can serve new bytes later.
    # Pinning it for a year would strand a stale logo with no way to bust it.
    await _upload_logo(authenticated_client)

    cache_control = (await client.get(f"/api/branding/logo{query}")).headers["cache-control"]

    assert "max-age=3600" in cache_control
    assert "immutable" not in cache_control


async def test_an_unset_image_is_an_uncached_404(client: httpx.AsyncClient) -> None:
    # Caching the miss would mask the next upload.
    resp = await client.get("/api/branding/logo")

    assert resp.status_code == 404
    assert "cache-control" not in resp.headers


async def test_a_dangling_file_reference_is_a_404_not_a_500(
    app,
    client: httpx.AsyncClient,
) -> None:
    # Settings hydrate from the DB, so the referenced file can be gone.
    app.state.branding.settings.logo_file_id = str(uuid.uuid4())

    assert (await client.get("/api/branding/logo")).status_code == 404


async def test_a_non_uuid_file_reference_is_a_404_not_a_500(
    app,
    client: httpx.AsyncClient,
) -> None:
    app.state.branding.settings.logo_file_id = "not-a-uuid"

    assert (await client.get("/api/branding/logo")).status_code == 404


# ── Response hardening ─────────────────────────────────────────────────


async def test_the_asset_response_cannot_be_rendered_as_a_document(
    stored_logo: StoredFile,
    authenticated_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
) -> None:
    # <img> and <link rel="icon"> ignore Content-Disposition, so the image
    # still renders — but a direct visit downloads instead of executing at our
    # origin, and nosniff pins the declared type.
    url = await _upload_logo(authenticated_client)

    resp = await client.get(url)

    assert resp.headers["content-disposition"] == "attachment"
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_the_prehydration_shell_carries_the_branded_favicon(
    stored_logo: StoredFile,
    app,
    authenticated_client: httpx.AsyncClient,
) -> None:
    # Without a server-rendered <link rel="icon"> the browser paints the
    # default favicon and only swaps once React hydrates — a visible flicker
    # on every full page load, most obviously on the sign-in page.
    app.state.branding.settings.favicon_file_id = str(stored_logo.id)

    page = await authenticated_client.get("/admin/branding/", follow_redirects=False)

    assert f'rel="icon" href="/api/branding/favicon?v={stored_logo.id}"' in page.text
