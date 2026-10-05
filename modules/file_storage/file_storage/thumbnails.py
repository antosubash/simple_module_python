"""Resized image variants for the browse grid, pickers and public pages (#352).

Variants are cached **in the storage backend**, beside the original, under a
key derived from the original's (``{key}.w{width}.webp``). That is the simplest
cache that is also robust: it survives restarts and is shared by every worker,
it needs no eviction policy of its own because the width is snapped to a short
whitelist (:data:`~file_storage.constants.THUMBNAIL_WIDTHS`, so at most five
variants per file), it inherits the original's tenant prefix, and it is dropped
with the original (:func:`delete_variants`). The cost is one extra object per
size actually requested.

Pillow work runs in a thread: decoding a large photo would otherwise stall the
event loop for every other request.
"""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from file_storage import constants
from file_storage.contracts.service import StorageNotFoundError

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend


class NotAnImageError(Exception):
    """The file's type has no thumbnail (not a raster image, or SVG)."""


class UnreadableImageError(Exception):
    """The bytes are not a decodable image, or are too large to decode safely."""


def is_thumbnailable(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() in constants.THUMBNAIL_SOURCE_TYPES


def snap_width(width: int | None) -> int:
    """Clamp to the allowed range, then round up to the next whitelisted size."""
    wanted = constants.THUMBNAIL_DEFAULT_WIDTH if width is None else width
    wanted = max(constants.THUMBNAIL_MIN_WIDTH, min(wanted, constants.THUMBNAIL_MAX_WIDTH))
    return next(w for w in constants.THUMBNAIL_WIDTHS if w >= wanted)


def variant_key(key: str, width: int) -> str:
    return f"{key}.w{width}.webp"


def render(data: bytes, width: int) -> bytes:
    """Resize ``data`` to at most ``width`` px wide, keeping aspect; WebP out.

    Never enlarges. The header is read lazily by ``Image.open``, so the pixel
    budget is checked *before* any decode — a few KB of PNG can declare a
    gigapixel canvas.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > constants.THUMBNAIL_MAX_PIXELS:
                raise UnreadableImageError("image exceeds the pixel budget")
            img.draft("RGB", (width * 2, width * 2))  # cheap JPEG downscale on decode
            img = ImageOps.exif_transpose(img)  # honour camera rotation
            img.thumbnail((width, width * 64), Image.Resampling.LANCZOS)
            mode = "RGBA" if img.mode in ("RGBA", "LA", "PA", "P") else "RGB"
            out = io.BytesIO()
            img.convert(mode).save(out, format="WEBP", quality=80)
            return out.getvalue()
    except UnreadableImageError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnreadableImageError(str(exc)) from exc


async def _read_all(backend: StorageBackend, key: str) -> bytes:
    return b"".join([chunk async for chunk in await backend.get(key)])


async def get_or_create(
    backend: StorageBackend, *, key: str, content_type: str, width: int | None
) -> tuple[bytes, int]:
    """The variant's bytes and the snapped width, generating it on first use."""
    if not is_thumbnailable(content_type):
        raise NotAnImageError(content_type)
    snapped = snap_width(width)
    cached_key = variant_key(key, snapped)
    try:
        return await _read_all(backend, cached_key), snapped
    except StorageNotFoundError:
        pass

    source = await _read_all(backend, key)
    data = await asyncio.to_thread(render, source, snapped)

    async def _once():
        yield data

    await backend.put(
        cached_key, _once(), content_type=constants.THUMBNAIL_CONTENT_TYPE, size=len(data)
    )
    return data, snapped


async def delete_variants(backend: StorageBackend, key: str) -> None:
    """Drop every cached variant of ``key``; absent ones are fine."""
    for width in constants.THUMBNAIL_WIDTHS:
        try:
            await backend.delete(variant_key(key, width))
        except Exception:
            continue
