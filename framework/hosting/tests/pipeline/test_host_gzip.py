"""Exercise host GZip with file ranges, media types and middleware overrides."""

import asyncio

import httpx
import pytest
from simple_module_hosting import disable_middleware, replace_middleware
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.pipeline.compression import HostGZipMiddleware
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

_BODY = b"text payload" * 4096
_REQUEST_HEADERS = {"Accept-Encoding": "gzip"}


async def test_static_range_keeps_original_bytes_and_headers(settings, tmp_path):
    (tmp_path / "asset.txt").write_bytes(_BODY)
    app = create_app(settings)
    app.mount("/health/range-files", StaticFiles(directory=tmp_path))

    async with (
        asyncio.timeout(5),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(
            "/health/range-files/asset.txt", headers={**_REQUEST_HEADERS, "Range": "bytes=0-16383"}
        )

    assert response.status_code == 206
    assert "content-encoding" not in response.headers
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == f"bytes 0-16383/{len(_BODY)}"
    assert response.content == _BODY[:16384]


@pytest.mark.parametrize(
    ("status", "media_type", "headers", "encoding"),
    [
        (200, "text/plain", None, "gzip"),
        (206, "text/plain", None, None),
        (200, "text/plain", {"Content-Range": "bytes 0-49151/98304"}, None),
        (200, "image/png", None, None),
        (200, "image/tiff", None, None),
        (200, "image/svg+xml", None, "gzip"),
        (200, "application/vnd.pmtiles", None, None),
    ],
)
async def test_host_gzip_response_selection(settings, status, media_type, headers, encoding):
    app = create_app(settings)

    @app.get("/health/gzip")
    async def payload():
        return Response(_BODY, status_code=status, media_type=media_type, headers=headers)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/gzip", headers=_REQUEST_HEADERS)

    assert response.status_code == status
    assert response.headers.get("content-encoding") == encoding
    if headers:
        assert response.headers["content-range"] == headers["Content-Range"]
    assert response.content == _BODY


@pytest.mark.parametrize("disable", [True, False], ids=["disabled", "custom_exclusions"])
async def test_host_gzip_override(settings, disable):
    def customize(app):
        if disable:
            disable_middleware(app, GZipMiddleware)
        else:
            replace_middleware(
                app,
                GZipMiddleware,
                Middleware(HostGZipMiddleware, exclude_content_types=("text/plain",)),
            )

    app = create_app(settings, customize=customize)

    @app.get("/health/gzip")
    async def payload():
        return Response(_BODY, media_type="text/plain")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/gzip", headers=_REQUEST_HEADERS)

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.content == _BODY


@pytest.mark.parametrize(
    ("excluded", "encoding"),
    [(None, "gzip"), (("image/*",), None)],
    ids=["default_list_compresses_svg", "explicit_image_wildcard_excludes_svg"],
)
async def test_svg_follows_explicit_image_wildcard(excluded, encoding):
    from starlette.applications import Starlette
    from starlette.routing import Route

    async def svg(request):
        return Response(_BODY, media_type="image/svg+xml")

    kwargs = {} if excluded is None else {"exclude_content_types": excluded}
    app = HostGZipMiddleware(Starlette(routes=[Route("/", svg)]), **kwargs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", headers=_REQUEST_HEADERS)

    assert response.headers.get("content-encoding") == encoding
