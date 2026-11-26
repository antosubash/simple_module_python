"""Thumbnail HEAD probes: cached size or a bounded, header-only source check."""

from __future__ import annotations

import asyncio
import struct
from typing import TYPE_CHECKING

from PIL import Image

from file_storage.contracts.service import StorageBackend, StorageNotFoundError
from file_storage.core import constants
from file_storage.files import thumbnails

if TYPE_CHECKING:
    from file_storage.files.service import FileStorageService
    from file_storage.models import StoredFile

_HEADER_PREFIXES = {
    "JPEG": (b"\xff\xd8\xff",),
    "PNG": (b"\x89PNG\r\n\x1a\n",),
    "GIF": (b"GIF87a", b"GIF89a"),
}


async def head_size_for_file(
    service: FileStorageService, row: StoredFile, width: int
) -> int | None:
    """Return the cached thumbnail size, or probe a cold source and return ``None``.

    Release the read connection before backend I/O, as GET does. ``width`` must
    already be snapped with :func:`thumbnails.snap_width`.
    """
    await service._release_connection(row)
    return await head_size(
        service.backend,
        key=row.key,
        content_type=row.content_type,
        width=width,
        source_size=row.size_bytes,
    )


async def head_size(
    backend: StorageBackend, *, key: str, content_type: str, width: int, source_size: int
) -> int | None:
    """Return the cached size, or check a cold source's bounded header prefix."""
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
    expected_format = thumbnails.expected_format(content_type)
    if expected_format == "WEBP" or (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        if expected_format != "WEBP":
            raise thumbnails.UnreadableImageError("content does not match the declared type")
        _check_webp_header(data)
        return
    try:
        with thumbnails.open_image(data, content_type):
            pass
    except (OSError, ValueError, EOFError, SyntaxError, struct.error) as exc:
        # A large JPEG may have more metadata than the probe budget. GET will
        # validate the remaining bytes; HEAD must keep its read bounded.
        if (
            partial
            and expected_format is not None
            and data.startswith(_HEADER_PREFIXES[expected_format])
        ):
            return
        raise thumbnails.UnreadableImageError(str(exc)) from exc
    except Image.DecompressionBombError as exc:
        raise thumbnails.UnreadableImageError(str(exc)) from exc


def _check_webp_header(data: bytes) -> None:
    # Pillow's WebP opener allocates a decoder canvas even without load().
    # Its dimension-only helper is private; keep this probe independent of it.
    # RIFF: 4-byte tag, 4-byte size, 4-byte WEBP tag, then an 8-byte chunk header.
    # The first chunk's payload therefore starts at byte 20.
    if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        raise thumbnails.UnreadableImageError("invalid WebP header")
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        # 3-byte frame tag + 3-byte keyframe sync code + two 16-bit dimensions.
        # Each dimension uses 14 bits; the high two bits encode scaling.
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
    elif chunk == b"VP8X" and len(data) >= 30 and data[16:20] == b"\x0a\0\0\0":
        # 10-byte payload: flags/reserved (4), then 24-bit width/height minus one.
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
    elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        # 0x2F signature + 32 packed bits: width-1 (14), height-1 (14), flags (4).
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    else:
        raise thumbnails.UnreadableImageError("invalid WebP header")
    if width == 0 or height == 0:
        raise thumbnails.UnreadableImageError("invalid WebP dimensions")
    if width * height > constants.THUMBNAIL_MAX_PIXELS:
        raise thumbnails.UnreadableImageError("image exceeds the pixel budget")
