"""Inline serving is an allow-list; everything else is a sandboxed attachment (#545)."""

from __future__ import annotations

import pytest
from file_storage import constants
from file_storage.media_types import is_active_content, normalise_media_type

API = constants.ROUTE_PREFIX_API

ACTIVE = [
    # The old deny-list's members, still refused.
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/xml",
    "application/xml",
    "text/javascript",
    "application/javascript",
    "application/x-shockwave-flash",
    # Scriptable XML the deny-list missed.
    "application/atom+xml",
    "application/rss+xml",
    "application/mathml+xml",
    "text/xsl",
    "application/vnd.wap.xhtml+xml",
    "application/xslt+xml",
    "video/x-something+xml",
    # Casing, parameters and whitespace no longer slip past an exact match.
    "Text/HTML",
    "TEXT/HTML; charset=utf-8",
    "  text/html  ",
    "image/SVG+XML;x=y",
    # Malformed: never cleaned up into something that looks safe.
    "text/html,",
    "image/png,text/html",
    "image/png text/html",
    "image/",
    "/png",
    "html",
    "",
    None,
    # Unknown types download rather than render.
    "application/octet-stream",
    "application/zip",
    "text/markdown",
]

INLINE = [
    "image/png",
    "IMAGE/PNG",
    "image/jpeg; q=0.9",
    "image/gif",
    "image/webp",
    "image/avif",
    "image/x-icon",
    "application/pdf",
    "application/json",
    "text/plain; charset=utf-8",
    "text/csv",
    "video/mp4",
    "audio/mpeg",
]


@pytest.mark.parametrize("content_type", ACTIVE)
def test_active(content_type):
    assert is_active_content(content_type) is True


@pytest.mark.parametrize("content_type", INLINE)
def test_inline_safe(content_type):
    assert is_active_content(content_type) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Image/PNG; charset=x", "image/png"),
        (" text/plain ", "text/plain"),
        ("application/rss+xml", "application/rss+xml"),
        ("text/html,", None),
        ("a/b/c", None),
        ("", None),
    ],
)
def test_normalise_media_type(raw, expected):
    assert normalise_media_type(raw) == expected


@pytest.mark.parametrize(
    ("ctype", "disposition"),
    [("application/rss+xml", "attachment"), ("text/xsl", "attachment"), ("image/png", "inline")],
)
async def test_public_route_applies_the_rule(authenticated_client, client, ctype, disposition):
    resp = await authenticated_client.post(
        f"{API}{constants.PATH_UPLOAD}",
        files={"file": ("f.bin", b"<x/>", ctype)},
        data={"public": "true"},
    )
    assert resp.status_code == 201, resp.text

    served = await client.get(f"{API}/public/{resp.json()['id']}")

    assert served.status_code == 200
    assert served.headers["content-disposition"].startswith(disposition)
    assert "sandbox" in served.headers["content-security-policy"]
