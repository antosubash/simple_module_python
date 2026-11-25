"""Thumbnail HEAD probes: cached size or a bounded, header-only source check."""

from __future__ import annotations

import asyncio
import io
import struct

from PIL import Image

from file_storage.contracts.service import StorageBackend, StorageNotFoundError
from file_storage.core import constants
from file_storage.files import thumbnails

_HEADER_PREFIXES = {
    "JPEG": (b"\xff\xd8\xff",),
    "PNG": (b"\x89PNG\r\n\x1a\n",),
    "GIF": (b"GIF87a", b"GIF89a"),
    "WEBP": (b"RIFF",),
}


async def head_size(
    backend: StorageBackend, *, key: str, content_type: str, width: int, source_size: int
) -> int | None:
    """Return the cached variant's size, or validate a cold source without rendering."""
    if not thumbnails.is_thumbnailable(content_type):
        raise thumbnails.NotAnImageError(content_type)
    cached_key = thumbnails.variant_key(key, width)
    head = getattr(backend, "head", None)
    if head is not None:
        try:
            return (await head(cached_key)).size
        except StorageNotFoundError:
            pass
    elif await backend.exists(cached_key):
        # Older third-party backends need not implement object metadata.
        return None

    if not await backend.exists(key):
        raise StorageNotFoundError(key)
    if source_size > constants.THUMBNAIL_MAX_SOURCE_BYTES:
        raise thumbnails.UnreadableImageError("source image is too large to thumbnail")
    limit = constants.THUMBNAIL_HEAD_PROBE_BYTES
    get_range = getattr(backend, "get_range", None)
    stream = (
        await get_range(key, 0, min(source_size, limit) - 1)
        if get_range is not None and source_size > 0
        else await backend.get(key)
    )
    data = bytearray()
    try:
        async for chunk in stream:
            data.extend(chunk[: limit - len(data)])
            if len(data) == limit:
                break
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()
    await asyncio.to_thread(_check_header, bytes(data), content_type, source_size > len(data))
    return None


def _check_header(data: bytes, content_type: str, partial: bool) -> None:
    expected_format = thumbnails._FORMATS_BY_TYPE[thumbnails.base_type(content_type)]
    try:
        img = Image.open(io.BytesIO(data), formats=thumbnails._ALLOWED_FORMATS)
    except (OSError, ValueError, EOFError, SyntaxError, struct.error) as exc:
        # A large JPEG may have more metadata than the probe budget. GET will
        # validate the remaining bytes; HEAD must keep its read bounded.
        if (
            partial
            and data.startswith(_HEADER_PREFIXES[expected_format])
            and (expected_format != "WEBP" or data[8:12] == b"WEBP")
        ):
            return
        raise thumbnails.UnreadableImageError(str(exc)) from exc
    except Image.DecompressionBombError as exc:
        raise thumbnails.UnreadableImageError(str(exc)) from exc
    with img:
        if img.format != expected_format:
            raise thumbnails.UnreadableImageError("content does not match the declared type")
        if img.width * img.height > constants.THUMBNAIL_MAX_PIXELS:
            raise thumbnails.UnreadableImageError("image exceeds the pixel budget")
