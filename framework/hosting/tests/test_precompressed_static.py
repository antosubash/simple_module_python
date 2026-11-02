"""Serving pre-compressed asset variants.

Compressing the same immutable, content-hashed bundle on every request is
wasted CPU, and on-the-fly compression has to use a fast (worse) level. Files
compressed once at build time can use the maximum level, and brotli is ~14%
smaller than gzip on this bundle.

The subtle part is the Content-Type: naively serving ``main.js.br`` makes
Starlette guess the type from the ``.br`` extension and the browser refuses to
execute it. These tests pin that behaviour.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import brotli
import httpx
import pytest
from fastapi import FastAPI
from simple_module_hosting.static_files import PrecompressedStaticFiles

_JS = b"console.log('hello');" * 200
_OK = 200
_JS_TYPE = "text/javascript"


@pytest.fixture
def asset_dir(tmp_path: Path) -> Path:
    (tmp_path / "app.js").write_bytes(_JS)
    (tmp_path / "app.js.gz").write_bytes(gzip.compress(_JS, 9))
    # A file with no pre-compressed sibling, to prove the fallback path.
    (tmp_path / "plain.js").write_bytes(_JS)
    return tmp_path


@pytest.fixture
def client(asset_dir: Path) -> httpx.AsyncClient:
    app = FastAPI()
    app.mount("/static", PrecompressedStaticFiles(directory=asset_dir), name="static")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


class TestPrecompressedServing:
    async def test_serves_gzip_sibling_when_accepted(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            "/static/app.js", headers={"Accept-Encoding": "gzip"}, extensions={"trust_env": False}
        )
        assert resp.status_code == _OK
        assert resp.headers["content-encoding"] == "gzip"

    async def test_content_type_is_the_original_not_the_variant(
        self, client: httpx.AsyncClient
    ) -> None:
        """The classic bug: .gz would otherwise be typed as octet-stream and
        the browser would refuse to execute the script."""
        resp = await client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        assert _JS_TYPE in resp.headers["content-type"]

    async def test_body_decodes_to_the_original_bytes(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        assert resp.content == _JS

    async def test_vary_header_is_set(self, client: httpx.AsyncClient) -> None:
        """Without Vary, a shared cache could serve a compressed body to a
        client that never asked for one."""
        resp = await client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        assert "accept-encoding" in resp.headers.get("vary", "").lower()

    async def test_identity_client_gets_uncompressed(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/static/app.js", headers={"Accept-Encoding": "identity"})
        assert resp.status_code == _OK
        assert "content-encoding" not in resp.headers
        assert resp.content == _JS

    async def test_missing_sibling_falls_back_to_original(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/static/plain.js", headers={"Accept-Encoding": "gzip, br"})
        assert resp.status_code == _OK
        assert "content-encoding" not in resp.headers
        assert resp.content == _JS

    async def test_unknown_file_still_404s(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/static/nope.js", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 404


class TestBrotliPreference:
    async def test_brotli_preferred_over_gzip(self, tmp_path: Path) -> None:
        """Brotli is ~14% smaller on this bundle, so it wins when both exist."""
        (tmp_path / "app.js").write_bytes(_JS)
        (tmp_path / "app.js.gz").write_bytes(gzip.compress(_JS, 9))
        (tmp_path / "app.js.br").write_bytes(brotli.compress(_JS))

        app = FastAPI()
        app.mount("/static", PrecompressedStaticFiles(directory=tmp_path), name="static")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.get("/static/app.js", headers={"Accept-Encoding": "gzip, deflate, br"})
        assert resp.headers["content-encoding"] == "br"

    async def test_gzip_used_when_brotli_not_accepted(self, tmp_path: Path) -> None:
        (tmp_path / "app.js").write_bytes(_JS)
        (tmp_path / "app.js.gz").write_bytes(gzip.compress(_JS, 9))
        (tmp_path / "app.js.br").write_bytes(brotli.compress(_JS))

        app = FastAPI()
        app.mount("/static", PrecompressedStaticFiles(directory=tmp_path), name="static")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        assert resp.headers["content-encoding"] == "gzip"


class TestImmutableCachingPreserved:
    """The existing immutable-caching behaviour must survive the refactor."""

    async def test_hashed_assets_keep_immutable_cache_control(self, tmp_path: Path) -> None:
        assets = tmp_path / "dist" / "assets"
        assets.mkdir(parents=True)
        (assets / "main-abc123.js").write_bytes(_JS)

        app = FastAPI()
        app.mount("/static", PrecompressedStaticFiles(directory=tmp_path), name="static")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.get("/static/dist/assets/main-abc123.js")
        assert "immutable" in resp.headers.get("cache-control", "")

    async def test_non_hashed_paths_do_not_get_immutable(self, tmp_path: Path) -> None:
        (tmp_path / "favicon.ico").write_bytes(b"\x00" * 100)

        app = FastAPI()
        app.mount("/static", PrecompressedStaticFiles(directory=tmp_path), name="static")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.get("/static/favicon.ico")
        assert "immutable" not in resp.headers.get("cache-control", "")
