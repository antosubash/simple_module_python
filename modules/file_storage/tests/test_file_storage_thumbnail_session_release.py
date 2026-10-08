"""A thumbnail request hands its DB connection back before the image work.

Generating a cold variant reads the original, waits for a decode slot and
decodes — none of which needs the database. Holding the request's session
(and so a pool connection) through all of that let a burst of cold anonymous
requests exhaust the pool.
"""

from __future__ import annotations

import io

import pytest
from file_storage import constants, thumbnails
from file_storage.visibility import FileStoragePublic
from PIL import Image

API = constants.ROUTE_PREFIX_API


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def observed(monkeypatch):
    """Record the request session's state at the moment generation runs."""
    seen: dict = {}
    original = FileStoragePublic.thumbnail

    async def spy(self, row, width):
        seen["db"] = self.db
        seen["row"] = row
        return await original(self, row, width)

    async def fake_generate(backend, *, key, content_type, width):
        db = seen["db"]
        seen["in_transaction"] = db.in_transaction()
        seen["row_attached"] = seen["row"] in db
        # Loaded attributes stay readable with no IO (no MissingGreenlet).
        seen["key_matches"] = seen["row"].key == key
        return b"fake-webp"

    monkeypatch.setattr(FileStoragePublic, "thumbnail", spy)
    monkeypatch.setattr(thumbnails, "get_or_create", fake_generate)
    return seen


async def _upload(client, **form) -> dict:
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}",
        files={"file": ("p.png", _png(), "image/png")},
        data=form,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_released(seen: dict) -> None:
    assert seen["in_transaction"] is False
    assert seen["row_attached"] is False
    assert seen["key_matches"] is True


async def test_public_thumbnail_releases_session_before_generating(
    authenticated_client, client, observed
):
    body = await _upload(authenticated_client, public="true")
    resp = await client.get(f"{API}/public/{body['id']}/thumbnail", params={"w": 64})
    assert resp.status_code == 200
    assert resp.content == b"fake-webp"
    _assert_released(observed)


async def test_authenticated_thumbnail_releases_session_before_generating(
    authenticated_client, observed
):
    body = await _upload(authenticated_client)
    resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail")
    assert resp.status_code == 200
    _assert_released(observed)
