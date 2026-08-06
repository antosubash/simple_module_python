"""Upload validation for branding images.

The declared ``Content-Type`` on a multipart part is chosen by the caller, so
it is a claim rather than a fact. An admin who uploads ``payload.html`` renamed
``logo.png`` would otherwise have it stored and later served back under an
``image/*`` type. Every accepted format therefore has to also *look* like
itself in its first bytes.

Mirrors the allow-list and signature check in the IIASA.GeoWiki Branding module
(``GeoWikiBrandingConsts``), including its deliberate omission of SVG.
"""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException, UploadFile

# Raster + icon only. SVG is excluded on purpose: it is an XML document that can
# carry <script>, so serving one back from our own origin would be stored XSS.
# The asset route defends in depth (attachment + nosniff), but the narrower
# allow-list is what actually keeps executable markup out of the store.
ALLOWED_IMAGE_TYPES: Final = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
)

MAX_IMAGE_BYTES: Final = 2 * 1024 * 1024  # 2 MB

ALLOWED_IMAGE_HINT: Final = "Allowed: PNG, JPEG, WEBP, GIF, ICO."

# Enough for the longest signature we test (WEBP needs 12 bytes).
_PROBE_BYTES: Final = 16

# (offset, literal) pairs; a format matches when every pair matches.
_SIGNATURES: Final[tuple[tuple[tuple[int, bytes], ...], ...]] = (
    ((0, b"\x89PNG\r\n\x1a\n"),),  # PNG
    ((0, b"\xff\xd8\xff"),),  # JPEG
    ((0, b"GIF87a"),),  # GIF
    ((0, b"GIF89a"),),
    ((0, b"RIFF"), (8, b"WEBP")),  # WEBP
    ((0, b"\x00\x00\x01\x00"),),  # ICO (Windows icon resource)
)


def normalize_content_type(raw: str | None) -> str:
    """Strip any ``; charset=…`` parameter and lowercase the media type."""
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip().lower()


def has_recognized_image_signature(head: bytes) -> bool:
    """True when ``head`` starts with the magic number of an allowed format."""
    return any(
        all(head[at : at + len(literal)] == literal for at, literal in signature)
        for signature in _SIGNATURES
    )


async def validate_image(file: UploadFile) -> None:
    """Reject anything that isn't a small, genuine raster/icon image.

    Leaves ``file`` rewound to the start so the caller can hand it straight to
    ``file_storage``.
    """
    content_type = normalize_content_type(file.content_type)
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type {content_type or 'unknown'!r}. {ALLOWED_IMAGE_HINT}",
        )

    # ``size`` is populated by Starlette's multipart parser. When it isn't (a
    # non-multipart caller), file_storage still enforces its own ceiling, so
    # this stays an early, friendlier guard rather than the only one.
    if file.size is not None and file.size > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds {MAX_IMAGE_BYTES} bytes.",
        )

    head = await file.read(_PROBE_BYTES)
    await file.seek(0)
    if not has_recognized_image_signature(head):
        raise HTTPException(
            status_code=415,
            detail=(
                f"File does not look like an image — its content does not match "
                f"{content_type!r}. {ALLOWED_IMAGE_HINT}"
            ),
        )
