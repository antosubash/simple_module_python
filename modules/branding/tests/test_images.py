"""Upload validation: the declared content-type is a claim, not a fact.

Mirrors ``GeoWikiBrandingConsts.HasRecognizedImageSignature`` in the
IIASA.GeoWiki Branding module — the same allow-list, the same magic-number
check, and the same deliberate exclusion of SVG.
"""

from __future__ import annotations

import io

import pytest
from branding.images import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    has_recognized_image_signature,
    normalize_content_type,
    validate_image,
)
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8
ICO = b"\x00\x00\x01\x00" + b"\x00" * 16


# ── Unit: signature sniffing ───────────────────────────────────────────


@pytest.mark.parametrize("data", [PNG, JPEG, GIF, WEBP, ICO])
def test_recognises_every_allowed_format(data: bytes) -> None:
    assert has_recognized_image_signature(data)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x89PNG",  # truncated PNG signature
        b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
        b"<!doctype html><script>alert(1)</script>",
        b"RIFF\x00\x00\x00\x00WAVE12345",  # RIFF container, but not WEBP
    ],
)
def test_rejects_anything_without_an_image_signature(data: bytes) -> None:
    assert not has_recognized_image_signature(data)


def test_svg_is_not_an_allowed_type() -> None:
    # Excluded on purpose: an SVG is an XML document that can carry <script>,
    # so serving one back from our own origin would be stored XSS.
    assert "image/svg+xml" not in ALLOWED_IMAGE_TYPES


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("image/png", "image/png"),
        ("IMAGE/PNG", "image/png"),
        ("image/png; charset=binary", "image/png"),
        ("  image/png  ", "image/png"),
        (None, ""),
    ],
)
def test_normalises_the_declared_content_type(raw: str | None, expected: str) -> None:
    # A charset parameter must not turn a legitimate PNG upload into a 415.
    assert normalize_content_type(raw) == expected


# ── Unit: validate_image ───────────────────────────────────────────────


def _make(data: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="logo.png",
        size=len(data),
        headers=Headers({"content-type": content_type}),
    )


async def test_accepts_a_genuine_png() -> None:
    upload = _make(PNG, "image/png")
    await validate_image(upload)
    # Left rewound so the caller can hand it straight to file_storage.
    assert await upload.read() == PNG


async def test_accepts_a_content_type_carrying_a_charset() -> None:
    await validate_image(_make(PNG, "image/png; charset=binary"))


async def test_rejects_a_disallowed_type() -> None:
    with pytest.raises(HTTPException) as exc:
        await validate_image(_make(PNG, "text/plain"))
    assert exc.value.status_code == 415


async def test_rejects_svg_even_though_it_is_an_image() -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    with pytest.raises(HTTPException) as exc:
        await validate_image(_make(svg, "image/svg+xml"))
    assert exc.value.status_code == 415


async def test_rejects_content_type_spoofing() -> None:
    # An HTML payload renamed logo.png and declared image/png. Without the
    # signature check it would be stored and later served under an image type.
    with pytest.raises(HTTPException) as exc:
        await validate_image(_make(b"<html><script>alert(1)</script></html>", "image/png"))
    assert exc.value.status_code == 415
    assert "does not look like an image" in str(exc.value.detail)


async def test_rejects_an_empty_upload() -> None:
    with pytest.raises(HTTPException) as exc:
        await validate_image(_make(b"", "image/png"))
    assert exc.value.status_code == 415


async def test_rejects_an_oversized_image() -> None:
    with pytest.raises(HTTPException) as exc:
        await validate_image(_make(PNG + b"\x00" * MAX_IMAGE_BYTES, "image/png"))
    assert exc.value.status_code == 413
