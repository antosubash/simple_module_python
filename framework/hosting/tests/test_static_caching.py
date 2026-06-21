"""ImmutableStaticFiles marks Vite's content-hashed assets immutable.

Hashed filenames (``main-3YbShAJ4.js``) are content-addressed, so browsers can
cache them forever and skip the per-asset revalidation round-trip. Non-hashed
paths keep StaticFiles' default (ETag/Last-Modified only).
"""

from __future__ import annotations

from pathlib import Path

from simple_module_hosting._phase_helpers import ImmutableStaticFiles

_GET_SCOPE = {"type": "http", "method": "GET", "headers": []}


def _make_tree(root: Path) -> None:
    (root / "dist" / "assets").mkdir(parents=True)
    (root / "dist" / "assets" / "main-ABC123.js").write_text("console.log(1)")
    (root / "dist" / ".vite").mkdir(parents=True)
    (root / "dist" / ".vite" / "manifest.json").write_text("{}")


async def test_hashed_asset_is_immutable(tmp_path: Path):
    _make_tree(tmp_path)
    static = ImmutableStaticFiles(directory=tmp_path)
    resp = await static.get_response("dist/assets/main-ABC123.js", _GET_SCOPE)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_non_asset_keeps_default_caching(tmp_path: Path):
    _make_tree(tmp_path)
    static = ImmutableStaticFiles(directory=tmp_path)
    resp = await static.get_response("dist/.vite/manifest.json", _GET_SCOPE)
    assert resp.status_code == 200
    assert "immutable" not in resp.headers.get("cache-control", "")
