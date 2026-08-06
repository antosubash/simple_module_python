"""A second logo for the app's always-dark surfaces.

The sidebar and mobile bar sit on ``--color-app-sidebar`` (near-black) in every
theme, while the auth card and public page are light. One uploaded logo cannot
read on both: dark ink vanishes in the sidebar, white ink vanishes on the auth
card. IIASA.GeoWiki solves this with ``BrandingImageType.LogoLight``/
``LogoDark``; this is the same idea, named for the *surface* rather than the
theme because here the sidebar is dark regardless of theme.

Purely additive: with no dark variant uploaded the payload reports ``None`` and
the frontend falls back to the primary logo, so existing sites are unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload
from file_storage.models import StoredFile
from file_storage.service import FileStorageService, StreamDownload

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[uuid.UUID, StoredFile]:
    rows: dict[uuid.UUID, StoredFile] = {}

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
        rows[row.id] = row
        return row

    async def fake_download(self: FileStorageService, file_id: uuid.UUID) -> StreamDownload:
        async def body() -> AsyncIterator[bytes]:
            yield _PNG

        return StreamDownload(file=rows[file_id], body=body())

    async def fake_delete(self: FileStorageService, file_id: uuid.UUID) -> StoredFile:
        return rows.pop(file_id)

    monkeypatch.setattr(FileStorageService, "upload", fake_upload, raising=True)
    monkeypatch.setattr(FileStorageService, "download", fake_download, raising=True)
    monkeypatch.setattr(FileStorageService, "delete", fake_delete, raising=True)
    return rows


# ── Unit: settings + payload ───────────────────────────────────────────


def test_defaults_to_no_dark_variant() -> None:
    assert BrandingSettings().logo_dark_file_id == ""


def test_payload_reports_no_dark_variant_as_none() -> None:
    # None is the signal for "fall back to logoUrl" on the frontend.
    assert branding_payload(BrandingSettings(logo_file_id="abc"))["logoDarkUrl"] is None


def test_payload_carries_the_dark_variant_on_its_own_route() -> None:
    payload = branding_payload(BrandingSettings(logo_file_id="abc", logo_dark_file_id="def"))
    assert payload["logoUrl"] == "/api/branding/logo?v=abc"
    assert payload["logoDarkUrl"] == "/api/branding/logo-dark?v=def"


# ── Integration: upload, serve, clear ──────────────────────────────────


async def test_uploading_a_dark_logo_leaves_the_primary_logo_alone(
    stored: dict[uuid.UUID, StoredFile],
    app,
    authenticated_client: httpx.AsyncClient,
) -> None:
    await authenticated_client.post(
        "/api/branding/logo", files={"file": ("l.png", _PNG, "image/png")}
    )
    primary = app.state.branding.settings.logo_file_id

    resp = await authenticated_client.post(
        "/api/branding/logo-dark", files={"file": ("d.png", _PNG, "image/png")}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert app.state.branding.settings.logo_file_id == primary
    assert body["logo_url"] == f"/api/branding/logo?v={primary}"
    assert body["logo_dark_url"].startswith("/api/branding/logo-dark?v=")


async def test_the_dark_logo_is_fetchable_by_a_logged_out_visitor(
    stored: dict[uuid.UUID, StoredFile],
    authenticated_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
) -> None:
    # It renders in the sidebar, which a guest never sees — but the shared prop
    # is emitted on guest pages too, so the route has to behave like its sibling.
    resp = await authenticated_client.post(
        "/api/branding/logo-dark", files={"file": ("d.png", _PNG, "image/png")}
    )
    url = resp.json()["logo_dark_url"]

    guest = await client.get(url, follow_redirects=False)

    assert guest.status_code == 200
    assert guest.content == _PNG


async def test_uploading_a_dark_logo_still_requires_authentication(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        "/api/branding/logo-dark", files={"file": ("d.png", _PNG, "image/png")}
    )
    assert resp.status_code in (401, 403)


async def test_clearing_the_dark_logo_reverts_to_the_primary(
    stored: dict[uuid.UUID, StoredFile],
    authenticated_client: httpx.AsyncClient,
) -> None:
    await authenticated_client.post(
        "/api/branding/logo", files={"file": ("l.png", _PNG, "image/png")}
    )
    await authenticated_client.post(
        "/api/branding/logo-dark", files={"file": ("d.png", _PNG, "image/png")}
    )

    resp = await authenticated_client.delete("/api/branding/logo-dark")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["logo_dark_url"] is None
    assert body["logo_url"] is not None


async def test_replacing_the_dark_logo_reaps_the_previous_one(
    stored: dict[uuid.UUID, StoredFile],
    authenticated_client: httpx.AsyncClient,
) -> None:
    first = await authenticated_client.post(
        "/api/branding/logo-dark", files={"file": ("d.png", _PNG, "image/png")}
    )
    first_id = first.json()["logo_dark_url"].split("=")[-1]

    await authenticated_client.post(
        "/api/branding/logo-dark", files={"file": ("d2.png", _PNG, "image/png")}
    )

    assert uuid.UUID(first_id) not in stored, "the replaced dark logo was orphaned"


async def test_an_unset_dark_logo_is_a_404(client: httpx.AsyncClient) -> None:
    # The frontend never requests it in this state — it falls back to logoUrl —
    # but a hand-typed URL must not 500.
    assert (await client.get("/api/branding/logo-dark")).status_code == 404
