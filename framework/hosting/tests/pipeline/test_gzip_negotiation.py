"""GZip negotiation respects explicit refusals and wildcard preferences."""

import httpx
import pytest
from simple_module_hosting.pipeline import compression
from starlette.responses import Response


@pytest.mark.parametrize(
    ("accept_encoding", "encoding"),
    [
        ("gzip;q=0, identity", None),
        ("identity;q=1, gzip;q=0", None),
        ("gzip;q=0, *;q=1", None),
        ("identity", None),
        ("*", "gzip"),
        ("*;q=0", None),
        ("GZip ; Q = 0.5", "gzip"),
        ("x-gzip", "gzip"),
        ("gzip;q=broken", None),
        ("gzip;q=broken, *", None),
        ("*, x-gzip;q=broken", None),
    ],
)
async def test_middleware_negotiates_gzip(accept_encoding, encoding):
    body = b"payload" * 300
    app = compression.HostGZipMiddleware(Response(body, media_type="text/plain"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", headers={"Accept-Encoding": accept_encoding})

    assert response.headers.get("content-encoding") == encoding
    assert response.content == body
    assert "accept-encoding" in response.headers["vary"].lower()


@pytest.mark.parametrize(
    ("values", "encoding"), [(("*", "gzip;q=0"), None), (("*;q=0", "gzip"), "gzip")]
)
async def test_middleware_combines_accept_encoding_fields(values, encoding):
    body = b"payload" * 300
    app = compression.HostGZipMiddleware(Response(body, media_type="text/plain"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", headers=[("Accept-Encoding", value) for value in values])

    assert response.headers.get("content-encoding") == encoding
    assert response.content == body


async def test_wildcard_keeps_small_response_uncompressed():
    body = b"small payload"
    app = compression.HostGZipMiddleware(Response(body, media_type="text/plain"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", headers={"Accept-Encoding": "*"})

    assert "content-encoding" not in response.headers
    assert "vary" not in response.headers
    assert response.headers["content-length"] == str(len(body))
    assert response.content == body


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("", False),
        ("identity", False),
        ("br, deflate", False),
        ("notgzip", False),
        ("gzip", True),
        ("gzip;q=0", False),
        ("gzip;q=0.000", False),
        ("gzip;q=0.001", True),
        ("gzip;q=1.000", True),
        ("gzip;q=1.", True),
        ("gzip;q=0.", False),
        ("x-gzip;q=0.5", True),
        ("X-GZIP;q=0", False),
        (" GZiP \t; Q = 0.5 , br ", True),
        ("*", True),
        ("*;q=0", False),
        ("br, *;q=0.5", True),
        ("gzip;q=0, *", False),
        ("*, gzip;q=0", False),
        ("*;q=0, gzip;q=0.1", True),
        ("x-gzip;q=0, *", False),
        ("gzip;q=broken, *", False),
        ("gzip;q=broken, gzip;q=0.5", True),
        (", , gzip,", True),
    ],
)
def test_accepts_gzip(value, accepted):
    assert compression._accepts_gzip(value) is accepted


@pytest.mark.parametrize(
    "quality",
    ["", "-0.1", "1.1", "2", "nan", "inf", "+0.5", ".5", "0.1234", '"0.5"', "0.5;q=1"],
)
def test_malformed_quality_is_treated_as_zero(quality):
    assert compression._accepts_gzip(f"gzip;q={quality}") is False
    assert compression._accepts_gzip(f"gzip;q={quality}, *") is False
    assert compression._accepts_gzip(f"*;q={quality}") is False
