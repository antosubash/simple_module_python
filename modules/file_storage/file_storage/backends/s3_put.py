"""Bounded server-side S3 uploads, including streams of unknown size (#708)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Any

from file_storage import constants, upload_support
from file_storage.contracts.service import Part, StorageBackendError
from file_storage.upload_support import SizeMismatchError

if TYPE_CHECKING:
    from file_storage.backends.s3 import S3Backend

logger = logging.getLogger(__name__)


# Replay blocks are read from disk once per executor hop; keep them well above the
# request-chunk size so a rolled-over spool costs few hops, yet bounded.
_REPLAY_BLOCK = 1024 * 1024
# Larger in-memory writes grow the BytesIO enough to stall the loop; offload them.
_INLINE_WRITE_LIMIT = 2 * 1024 * 1024


class _Buf:
    """A SpooledTemporaryFile whose in-memory operations run inline.

    Executor hops cost more than a memcpy, so only operations that touch disk (the
    spool already rolled over, or this write would roll it) are offloaded.
    """

    def __init__(self) -> None:
        self.max_size = constants.SPOOL_MAX_SIZE_BYTES
        self.file = SpooledTemporaryFile(max_size=self.max_size)  # noqa: SIM115 — closed in aclose
        self.pos = 0

    async def __aenter__(self) -> _Buf:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _in_memory(self) -> bool:
        # `_rolled` has no public API; missing -> treat as on disk.
        return not getattr(self.file, "_rolled", True)

    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        if self._in_memory():
            return fn(*args)
        return await _io(fn, *args)

    async def write(self, data: bytes | memoryview) -> None:
        # Growing a large BytesIO reallocates and faults pages: keep that off the loop too.
        if self._in_memory() and self.pos + len(data) <= min(self.max_size, _INLINE_WRITE_LIMIT):
            self.file.write(data)
        else:
            await _io(self.file.write, data)
        self.pos += len(data)

    async def read(self, size: int) -> bytes:
        return await self._call(self.file.read, size)

    async def rewind(self) -> None:
        self.pos = 0
        await self._call(self.file.seek, 0)

    async def reset(self) -> None:
        self.pos = 0
        await self._call(self._truncate_from_start)

    def _truncate_from_start(self) -> None:
        self.file.seek(0)
        self.file.truncate()

    async def aclose(self) -> None:
        await self._call(self.file.close)


async def put_stream(
    backend: S3Backend, key: str, stream: AsyncIterator[bytes], content_type: str, size: int
) -> None:
    """Buffer up to the threshold, then send one bounded part at a time."""
    if size < 0:
        raise ValueError("size must be nonnegative (0 means unknown)")
    threshold = min(backend.multipart_threshold_bytes, constants.MAX_S3_PART_SIZE_BYTES)
    iterator = aiter(stream)
    tail: memoryview | None = None
    async with _Buf() as prefix:
        if size <= threshold:
            async for chunk in iterator:
                take = min(len(chunk), threshold + 1 - prefix.pos)
                await prefix.write(memoryview(chunk)[:take])
                if prefix.pos > threshold:
                    tail = memoryview(chunk)[take:]
                    break
            else:
                length = prefix.pos
                if size and length != size:
                    raise SizeMismatchError(size, length)
                await prefix.rewind()
                try:
                    async with backend._client() as client:
                        await client.put_object(
                            Bucket=backend.bucket,
                            Key=key,
                            Body=prefix.file,
                            ContentType=content_type,
                            ContentLength=length,
                        )
                except Exception as exc:
                    raise StorageBackendError(f"S3 put_object failed: {exc}") from exc
                return
        await prefix.rewind()

        async def body() -> AsyncIterator[bytes]:
            while chunk := await prefix.read(_REPLAY_BLOCK):
                yield chunk
            if tail:
                yield bytes(tail)
            async for chunk in iterator:
                yield chunk

        await _multipart(backend, key, body(), content_type, size)


async def _multipart(backend: S3Backend, key, stream, content_type, size) -> None:
    part_size = upload_support.choose_part_size(size, backend.multipart_part_size_bytes)
    if part_size > constants.MAX_S3_PART_SIZE_BYTES:
        raise ValueError("S3 part size exceeds 5 GiB")
    async with backend._client() as client:
        await _upload(client, backend, key, stream, content_type, size, part_size)


async def _upload(client, backend, key, stream, content_type, size, part_size) -> None:
    upload_id = await backend._create_multipart_on(client, key, content_type)
    parts: list[Part] = []
    seen = 0
    try:
        async with _Buf() as buf:
            async for chunk in stream:
                seen += len(chunk)
                if size and seen > size:
                    raise SizeMismatchError(size, seen)
                remaining = memoryview(chunk)
                while remaining:
                    take = min(len(remaining), part_size - buf.pos)
                    await buf.write(remaining[:take])
                    remaining = remaining[take:]
                    if buf.pos == part_size:
                        parts.append(await _send(client, backend, key, upload_id, parts, buf))
                        await buf.reset()
            if size and seen != size:
                raise SizeMismatchError(size, seen)
            if buf.pos or not parts:
                parts.append(await _send(client, backend, key, upload_id, parts, buf))
        await backend._complete_multipart_on(client, key, upload_id, parts)
    except BaseException:
        try:
            await backend._abort_multipart_on(client, key, upload_id)
        except BaseException:
            logger.exception("file_storage.server_upload_abort_failed key=%s", key)
        raise


async def _send(client, backend: S3Backend, key, upload_id, parts, buf: _Buf) -> Part:
    number = len(parts) + 1
    if number > constants.MAX_UPLOAD_PARTS:
        raise ValueError("S3 upload exceeds maximum part count")
    length = buf.pos
    await buf.rewind()
    try:
        result = await client.upload_part(
            Bucket=backend.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=number,
            Body=buf.file,
            ContentLength=length,
        )
    except Exception as exc:
        raise StorageBackendError(f"S3 upload_part failed: {exc}") from exc
    return Part(no=number, etag=result["ETag"], size=length)


async def _io(fn: Callable[..., Any], *args: Any) -> Any:
    # Finish in-flight I/O before cancellation can close or reuse its spool.
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                # The I/O task itself was cancelled (loop shutdown cancels every task):
                # nothing is in flight, and shielding it again would spin forever.
                raise
            cancelled = exc
        except BaseException:
            if cancelled is not None:
                raise cancelled from None
            raise
    if cancelled is not None:
        raise cancelled
    return result
