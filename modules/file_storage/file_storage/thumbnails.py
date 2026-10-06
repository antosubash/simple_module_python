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
import struct
import weakref
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


def base_type(content_type: str) -> str:
    """The media type without parameters, lowercased (``Image/PNG; x=y`` -> ``image/png``)."""
    return content_type.split(";")[0].strip().lower()


def is_thumbnailable(content_type: str) -> bool:
    return base_type(content_type) in _FORMATS_BY_TYPE


def snap_width(width: int | None) -> int:
    """Clamp to the allowed range, then round up to the next whitelisted size."""
    wanted = constants.THUMBNAIL_DEFAULT_WIDTH if width is None else width
    wanted = max(constants.THUMBNAIL_MIN_WIDTH, min(wanted, constants.THUMBNAIL_MAX_WIDTH))
    return next(w for w in constants.THUMBNAIL_WIDTHS if w >= wanted)


def variant_key(key: str, width: int) -> str:
    return f"{key}.w{width}.webp"


_FORMATS_BY_TYPE = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}
# Pillow's decoders are a large native attack surface; only these four are ever
# opened (``formats=``), never SVG/EPS/PSD/TIFF/PDF-style containers.
_ALLOWED_FORMATS = tuple(_FORMATS_BY_TYPE.values())

# At most this many decodes run at once, so a burst of cold-cache requests
# cannot pin every CPU or hold N decoded canvases in memory together. One
# semaphore per event loop (an asyncio primitive belongs to one loop).
_SLOTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)
# Single-flight: concurrent cold requests for one variant share one decode.
_INFLIGHT: dict[tuple[int, str], asyncio.Task[bytes]] = {}


def _slots() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _SLOTS:
        _SLOTS[loop] = asyncio.Semaphore(constants.THUMBNAIL_MAX_CONCURRENCY)
    return _SLOTS[loop]


def render(data: bytes, width: int, content_type: str | None = None) -> bytes:
    """Resize ``data`` to at most ``width`` px wide, keeping aspect; WebP out.

    Never enlarges. The header is parsed lazily by ``Image.open``, so the pixel
    budget is checked *before* any decode — a few KB of PNG can declare a
    gigapixel canvas. The sniffed format must be on the allowlist *and* match
    the declared content type (a ``.png`` that is really a PSD is refused).
    Animated inputs yield their first frame; the output is re-encoded from
    pixels only, so EXIF/XMP/ICC and other metadata are not carried over.
    """
    try:
        with Image.open(io.BytesIO(data), formats=_ALLOWED_FORMATS) as img:
            if content_type is not None and img.format != _FORMATS_BY_TYPE.get(
                base_type(content_type)
            ):
                raise UnreadableImageError("content does not match the declared type")
            # Header-only so far: refuse before any pixel is decoded. This is
            # our own budget; the process-wide ``Image.MAX_IMAGE_PIXELS`` is
            # left alone (it is shared with every other Pillow user and racy
            # to mutate from worker threads).
            if img.width * img.height > constants.THUMBNAIL_MAX_PIXELS:
                raise UnreadableImageError("image exceeds the pixel budget")
            img.seek(0)  # first frame only
            img.draft("RGB", (width * 2, width * 2))  # cheap JPEG downscale on decode
            frame = _to_8bit(ImageOps.exif_transpose(img))
            frame.thumbnail((width, width * 64), Image.Resampling.LANCZOS)
            mode = "RGBA" if frame.mode in ("RGBA", "LA", "PA", "P") else "RGB"
            out = io.BytesIO()
            frame.convert(mode).save(out, format="WEBP", quality=80)
            return out.getvalue()
    except UnreadableImageError:
        raise
    except (
        OSError,
        ValueError,
        EOFError,
        SyntaxError,  # Pillow raises this for some malformed PNG/ICO chunks
        struct.error,
        Image.DecompressionBombError,
    ) as exc:
        raise UnreadableImageError(str(exc)) from exc


_WIDE_GRAY_MODES = frozenset({"I", "I;16", "I;16B", "I;16L", "I;16N"})


def _to_8bit(frame: Image.Image) -> Image.Image:
    """Map 16/32-bit grayscale (a 16-bit PNG opens as ``I;16``) onto 8-bit ``L``.

    Pillow cannot ``reduce()`` these modes, which ``thumbnail`` uses for large
    downscales, so a valid 16-bit PNG would render at some widths and fail at
    others. Scaled by 1/256 rather than clipped, so a 16-bit image keeps its
    tones instead of turning almost entirely white. Runs after the pixel-budget
    check, so the wider intermediate is bounded like every other decode.
    """
    if frame.mode not in _WIDE_GRAY_MODES:
        return frame
    return frame.convert("I").point(lambda v: v * (1 / 256)).convert("L")


async def _read_all(backend: StorageBackend, key: str, *, limit: int | None = None) -> bytes:
    """Whole object, aborting once ``limit`` bytes are exceeded (no unbounded buffer)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in await backend.get(key):
        total += len(chunk)
        if limit is not None and total > limit:
            raise UnreadableImageError("source image is too large to thumbnail")
        chunks.append(chunk)
    return b"".join(chunks)


async def get_or_create(
    backend: StorageBackend, *, key: str, content_type: str, width: int
) -> bytes:
    """The variant's bytes, generating it on first use.

    ``width`` must already be snapped (:func:`snap_width`) so the number of
    cached variants stays bounded.
    """
    if not is_thumbnailable(content_type):
        raise NotAnImageError(content_type)
    cached_key = variant_key(key, width)
    try:
        return await _read_all(backend, cached_key)
    except StorageNotFoundError:
        pass

    # The work runs in its own task and callers only *await* it through
    # ``shield``: a client that disconnects cancels its wait, not the decode,
    # so the semaphore slot is held until the worker thread has really
    # finished and abort-and-retry loops cannot multiply concurrent decodes.
    flight = (id(asyncio.get_running_loop()), cached_key)
    task = _INFLIGHT.get(flight)
    if task is None:
        task = asyncio.ensure_future(_generate(backend, key, cached_key, content_type, width))
        _INFLIGHT[flight] = task
        task.add_done_callback(
            lambda t: (_INFLIGHT.pop(flight, None), t.cancelled() or t.exception())
        )
    return await asyncio.shield(task)


async def _generate(
    backend: StorageBackend, key: str, cached_key: str, content_type: str, width: int
) -> bytes:
    async with _slots():
        source = await _read_all(backend, key, limit=constants.THUMBNAIL_MAX_SOURCE_BYTES)
        data = await asyncio.to_thread(render, source, width, content_type)

    async def _once():
        yield data

    await backend.put(
        cached_key, _once(), content_type=constants.THUMBNAIL_CONTENT_TYPE, size=len(data)
    )
    return data


async def delete_variants(backend: StorageBackend, key: str) -> None:
    """Drop every cached variant of ``key``; absent ones are fine."""
    await asyncio.gather(
        *(backend.delete(variant_key(key, width)) for width in constants.THUMBNAIL_WIDTHS),
        return_exceptions=True,
    )
