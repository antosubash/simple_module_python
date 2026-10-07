"""Thumbnails (#352) and list search/filter/sort (#352)."""

from __future__ import annotations

import io

from file_storage import constants, thumbnails
from PIL import Image

API = constants.ROUTE_PREFIX_API


def _png(width=2000, height=1000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def _upload(client, name, data, ctype, **form):
    resp = await client.post(
        f"{API}{constants.PATH_UPLOAD}", files={"file": (name, data, ctype)}, data=form
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _size(content: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(content)) as img:
        return img.size


def test_snap_width_clamps_and_rounds_up():
    assert thumbnails.snap_width(None) == 256
    assert thumbnails.snap_width(1) == 64
    assert thumbnails.snap_width(100) == 128
    assert thumbnails.snap_width(5000) == 1024


async def test_thumbnail_sizes_preserve_aspect(authenticated_client):
    body = await _upload(authenticated_client, "p.png", _png(), "image/png")
    for w, expected in ((100, 128), (None, 256), (9999, 1024)):
        url = f"{API}/files/{body['id']}/thumbnail"
        resp = await authenticated_client.get(url, params={"w": w} if w else None)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/webp"
        width, height = _size(resp.content)
        assert width == expected
        assert height == expected // 2


async def test_thumbnail_never_enlarges(authenticated_client):
    body = await _upload(authenticated_client, "s.png", _png(40, 20), "image/png")
    resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail", params={"w": 512})
    assert _size(resp.content) == (40, 20)


async def test_thumbnail_non_image_and_svg_404(authenticated_client):
    txt = await _upload(authenticated_client, "a.txt", b"hi", "text/plain")
    svg = await _upload(authenticated_client, "a.svg", b"<svg/>", "image/svg+xml")
    for body in (txt, svg):
        resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail")
        assert resp.status_code == 404


async def test_corrupt_image_is_422(authenticated_client):
    body = await _upload(authenticated_client, "bad.png", b"not a png", "image/png")
    resp = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail")
    assert resp.status_code == 422


def test_pixel_budget_refused_before_decode(monkeypatch):
    monkeypatch.setattr(constants, "THUMBNAIL_MAX_PIXELS", 100)
    try:
        thumbnails.render(_png(50, 50), 64)
    except thumbnails.UnreadableImageError:
        return
    raise AssertionError("expected UnreadableImageError")


async def test_thumbnail_is_cached_in_backend(app, authenticated_client):
    body = await _upload(authenticated_client, "p.png", _png(), "image/png")
    backend = app.state.file_storage.backend
    key = body["key"]
    assert not await backend.exists(thumbnails.variant_key(key, 128))
    first = await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail", params={"w": 128})
    assert await backend.exists(thumbnails.variant_key(key, 128))

    # Replace the source: a cache hit must not re-read or re-render it.
    async def _gen():
        yield b"garbage"

    await backend.put(key, _gen(), content_type="image/png", size=7)
    second = await authenticated_client.get(
        f"{API}/files/{body['id']}/thumbnail", params={"w": 100}
    )
    assert second.status_code == 200
    assert second.content == first.content


async def test_delete_drops_variants(app, authenticated_client):
    body = await _upload(authenticated_client, "p.png", _png(), "image/png")
    await authenticated_client.get(f"{API}/files/{body['id']}/thumbnail", params={"w": 128})
    backend = app.state.file_storage.backend
    await authenticated_client.delete(f"{API}/files/{body['id']}")
    assert not await backend.exists(thumbnails.variant_key(body["key"], 128))


async def test_public_thumbnail(authenticated_client, client):
    pub = await _upload(authenticated_client, "p.png", _png(), "image/png", public="true")
    priv = await _upload(authenticated_client, "q.png", _png(), "image/png")
    resp = await client.get(f"{API}/public/{pub['id']}/thumbnail", params={"w": 64})
    assert resp.status_code == 200
    assert resp.headers["cache-control"].startswith("public")
    assert _size(resp.content)[0] == 64
    assert (await client.get(f"{API}/public/{priv['id']}/thumbnail")).status_code == 404


# ── list search / filter / sort ──────────────────────────────────────


async def _seed(client):
    for name, data, ctype in (
        ("Alpha.png", b"1", "image/png"),
        ("beta.jpg", b"22", "image/jpeg"),
        ("100%_done.txt", b"333", "text/plain"),
        ("gamma.pdf", b"4444", "application/pdf"),
    ):
        await _upload(client, name, data, ctype)


async def _names(client, **params):
    resp = await client.get(f"{API}/files", params=params)
    assert resp.status_code == 200, resp.text
    return [i["filename"] for i in resp.json()["items"]], resp.json()["total"]


async def test_list_search_is_case_insensitive_substring(authenticated_client):
    await _seed(authenticated_client)
    assert (await _names(authenticated_client, q="ALPH"))[0] == ["Alpha.png"]
    assert (await _names(authenticated_client, q="a"))[1] == 3


async def test_list_search_escapes_like_wildcards(authenticated_client):
    await _seed(authenticated_client)
    assert (await _names(authenticated_client, q="%"))[0] == ["100%_done.txt"]
    assert (await _names(authenticated_client, q="_"))[0] == ["100%_done.txt"]
    assert (await _names(authenticated_client, q="0%_d"))[0] == ["100%_done.txt"]


async def test_list_content_type_exact_and_prefix(authenticated_client):
    await _seed(authenticated_client)
    names, total = await _names(authenticated_client, content_type="image/", sort="name")
    assert names == ["Alpha.png", "beta.jpg"] and total == 2
    assert (await _names(authenticated_client, content_type="image/png"))[0] == ["Alpha.png"]
    assert (await _names(authenticated_client, content_type="application/pdf"))[1] == 1


async def test_list_sort_orders(authenticated_client):
    await _seed(authenticated_client)
    assert (await _names(authenticated_client, sort="name"))[0] == [
        "100%_done.txt",
        "Alpha.png",
        "beta.jpg",
        "gamma.pdf",
    ]
    assert (await _names(authenticated_client, sort="-name"))[0][0] == "gamma.pdf"
    assert (await _names(authenticated_client, sort="size"))[0][0] == "Alpha.png"
    assert (await _names(authenticated_client, sort="-size"))[0][0] == "gamma.pdf"
    assert (await _names(authenticated_client, sort="created_at"))[0][0] == "Alpha.png"
    # default is newest first
    assert (await _names(authenticated_client))[0][0] == "gamma.pdf"


async def test_list_rejects_unknown_sort(authenticated_client):
    resp = await authenticated_client.get(f"{API}/files", params={"sort": "bogus"})
    assert resp.status_code == 422
