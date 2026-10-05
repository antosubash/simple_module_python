"""Pillow attack-surface limits and tenant/permission edges of the new routes."""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from file_storage import constants, thumbnails
from PIL import Image

API = constants.ROUTE_PREFIX_API


def _png(width=200, height=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def _upload(client, name, data, ctype, **form):
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}", files={"file": (name, data, ctype)}, data=form
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_animated_gif_yields_first_frame_only():
    buf = io.BytesIO()
    frames = [Image.new("RGB", (300, 150), c) for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    out = thumbnails.render(buf.getvalue(), 128, "image/gif")
    with Image.open(io.BytesIO(out)) as img:
        assert getattr(img, "n_frames", 1) == 1
        assert img.size == (128, 64)


def test_exif_metadata_is_not_carried_over():
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "secret description"
    Image.new("RGB", (200, 100)).save(buf, format="JPEG", exif=exif)
    out = thumbnails.render(buf.getvalue(), 128, "image/jpeg")
    assert b"secret description" not in out
    with Image.open(io.BytesIO(out)) as img:
        assert not img.getexif()


def test_sniffed_format_must_match_declared_type():
    with pytest.raises(thumbnails.UnreadableImageError):
        thumbnails.render(_png(10, 10), 64, "image/jpeg")


def test_formats_outside_the_allowlist_are_refused():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="BMP")
    with pytest.raises(thumbnails.UnreadableImageError):
        thumbnails.render(buf.getvalue(), 64, "image/png")


def test_pixel_budget_applies_even_under_bomb_warning(monkeypatch):
    monkeypatch.setattr(constants, "THUMBNAIL_MAX_PIXELS", 100)
    with pytest.raises(thumbnails.UnreadableImageError):
        thumbnails.render(_png(50, 50), 64, "image/png")


async def test_oversized_source_is_refused_before_decode(authenticated_client, monkeypatch):
    body = await _upload(authenticated_client, "p.png", _png(), "image/png")
    monkeypatch.setattr(constants, "THUMBNAIL_MAX_SOURCE_BYTES", 10)
    resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail", params={"w": 64})
    assert resp.status_code == 422


async def test_mislabelled_upload_is_422(authenticated_client):
    body = await _upload(authenticated_client, "x.png", b"<svg xmlns='x'/>", "image/png")
    resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail")
    assert resp.status_code == 422


async def test_other_tenants_file_is_invisible_to_patch_thumbnail_download(
    app, authenticated_client
):
    from file_storage.models import StoredFile
    from simple_module_db import tenant_context

    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            row = StoredFile(
                key="acme/other.png",
                filename="other.png",
                content_type="image/png",
                size_bytes=1,
                backend=constants.BackendId.FILESYSTEM,
                checksum_sha256="0" * 64,
            )
            session.add(row)
            await session.flush()
            file_id = row.id
        await session.commit()
    url = f"{API}/files/{file_id}"
    assert (await authenticated_client.patch(url, json={"public": True})).status_code == 404
    assert (await authenticated_client.get(f"{url}/thumbnail")).status_code == 404
    assert (await authenticated_client.get(f"{url}/download")).status_code == 404


async def test_private_and_unknown_public_responses_are_identical(authenticated_client, client):
    body = await _upload(authenticated_client, "q.png", _png(), "image/png")
    private = await client.get(f"{API}/public/{body['id']}/thumbnail")
    unknown = await client.get(f"{API}/public/{uuid4()}/thumbnail")
    assert private.status_code == unknown.status_code == 404
    assert private.json() == unknown.json()


async def test_anonymous_cannot_use_authenticated_thumbnail(authenticated_client, client):
    body = await _upload(authenticated_client, "q.png", _png(), "image/png", public="true")
    resp = await client.get(f"{API}/files/{body['id']}/thumbnail")
    assert resp.status_code in (401, 302, 403)
