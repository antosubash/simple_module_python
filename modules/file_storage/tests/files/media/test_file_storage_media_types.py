"""Inline serving is an allow-list; everything else is a sandboxed attachment (#545)."""

from __future__ import annotations

import pytest
from file_storage.core import constants
from file_storage.files.media_types import is_active_content, normalise_media_type

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
    "image/png;x=1,text/html",
    'image/png; x="a,b"',
    "image/png text/html",
    "image/",
    "/png",
    "html",
    "",
    None,
    # Unknown types download rather than render.
    "text/markdown",
    "application/x-unknown",
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
    "font/woff2",
    "application/octet-stream",
    "application/zip",
    "application/geo+json",
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


def test_control_chars_rejected_and_safe_media_type_falls_back():
    from file_storage.core.settings import FileStorageSettings
    from file_storage.files.media_types import safe_media_type
    from file_storage.files.service import ContentTypeNotAllowedError, FileStorageService

    poisoned = "image/png; x=\r\nInjected: 1"
    assert normalise_media_type(poisoned) is None
    assert is_active_content(poisoned) is True
    assert safe_media_type(poisoned) == "application/octet-stream"
    assert safe_media_type("Image/PNG; charset=utf-8") == "image/png; charset=utf-8"
    assert safe_media_type("text/plain; charset=iso-8859-1") == "text/plain; charset=iso-8859-1"
    assert safe_media_type("image/png; invalid param!") == "image/png"

    svc = FileStorageService.__new__(FileStorageService)
    svc.settings = FileStorageSettings()
    with pytest.raises(ContentTypeNotAllowedError):
        svc._check_content_type(poisoned)


@pytest.mark.parametrize("charset", ["iso-8859-1", '"utf-8"'])
@pytest.mark.parametrize("separator", ["; ", ";; ", "; ; "])
async def test_downloads_sanitize_control_chars_and_preserve_safe_params(
    tmp_path, charset, separator
):
    from file_storage.backends.filesystem import FilesystemBackend
    from file_storage.files.downloads import presigned_download_url
    from file_storage.files.ranges import file_body_response
    from file_storage.models import StoredFile
    from starlette.requests import Request

    backend = FilesystemBackend(root=tmp_path)

    async def chunks():
        yield b"abcdef"

    await backend.put("ab/obj", chunks(), content_type="text/plain", size=6)
    poisoned_row = StoredFile(
        key="ab/obj",
        filename="f.txt",
        content_type="image/png; x=\r\nInjected: 1",
        size_bytes=6,
        backend="filesystem",
    )
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    resp = await file_body_response(backend, poisoned_row, req, headers={}, etag='"e"')
    assert resp.media_type == "application/octet-stream"

    iso_row = StoredFile(
        key="ab/obj",
        filename="f.txt",
        content_type=f"Text/Plain{separator}charset={charset}",
        size_bytes=6,
        backend="filesystem",
    )
    full = await file_body_response(backend, iso_row, req, headers={}, etag='"e"')
    assert full.headers["content-type"] == f"text/plain; charset={charset}"

    ranged_req = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [(b"range", b"bytes=0-2")]}
    )
    ranged = await file_body_response(backend, iso_row, ranged_req, headers={}, etag='"e"')
    assert ranged.status_code == 206
    assert ranged.headers["content-type"] == f"text/plain; charset={charset}"

    class _PresignBackend:
        backend_id = "filesystem"
        supports_presigned_url = True

        async def presigned_get_url(self, key, ttl_seconds, **headers):
            self.headers = headers
            return f"https://signed/{key}"

    pb = _PresignBackend()
    await presigned_download_url(pb, iso_row, 60, attachment=True)
    assert pb.headers["content_type"] == f"text/plain; charset={charset}"
    await presigned_download_url(pb, poisoned_row, 60, attachment=True)
    assert pb.headers["content_type"] == "application/octet-stream"


@pytest.mark.parametrize("parameter", ['charset="utf-8"', 'x="a,b;c"', r'x="a\"b"', 'x=""'])
def test_quoted_response_parameters_do_not_relax_inline_safety(parameter):
    from file_storage.files.media_types import safe_media_type

    raw = f"text/plain; {parameter}"
    assert safe_media_type(raw) == raw
    assert normalise_media_type(raw) is None
    assert is_active_content(raw) is True


@pytest.mark.parametrize("separator", [";; ", "; ; "])
@pytest.mark.parametrize("charset", ["iso-8859-1", '"iso-8859-1"'])
def test_empty_parameters_preserve_charset(separator, charset):
    from file_storage.files.media_types import safe_media_type

    raw = f"text/plain{separator}charset={charset}; x=ok{separator}y=last; ; "
    assert safe_media_type(raw) == f"text/plain; charset={charset}; x=ok; y=last"


@pytest.mark.parametrize(
    ("parameter", "expected"),
    [
        ('x="unclosed', "application/octet-stream"),
        ('x="a"junk', "text/plain"),
        ("x=a,text/html", "application/octet-stream"),
        ('x="a",text/html', "application/octet-stream"),
        ('x="a\r\nb"', "application/octet-stream"),
        ('x="a\tb"', "application/octet-stream"),
    ],
)
def test_malformed_response_parameters_use_safe_fallback(parameter, expected):
    from file_storage.files.media_types import safe_media_type

    assert safe_media_type(f"text/plain; {parameter}") == expected
