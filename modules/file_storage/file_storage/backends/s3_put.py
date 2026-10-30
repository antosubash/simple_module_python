"""Bounded server-side S3 uploads, including streams of unknown size (#708)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING

from file_storage import constants, upload_support
from file_storage.contracts.service import Part, StorageBackendError
from file_storage.upload_support import SizeMismatchError

if TYPE_CHECKING:
    from file_storage.backends.s3 import S3Backend

logger = logging.getLogger(__name__)


async def put_stream(
    backend: S3Backend, key: str, stream: AsyncIterator[bytes], content_type: str, size: int
) -> None:
    """Buffer up to the threshold, then send one bounded part at a time."""
    if size < 0:
        raise ValueError("size must be nonnegative (0 means unknown)")
    threshold = min(backend.multipart_threshold_bytes, constants.MAX_S3_PART_SIZE_BYTES)
    iterator = aiter(stream)
    tail: memoryview | None = None
    with SpooledTemporaryFile(max_size=constants.SPOOL_MAX_SIZE_BYTES) as prefix:
        if size <= threshold:
            async for chunk in iterator:
                take = min(len(chunk), threshold + 1 - prefix.tell())
                prefix.write(memoryview(chunk)[:take])
                if prefix.tell() > threshold:
                    tail = memoryview(chunk)[take:]
                    break
            else:
                length = prefix.tell()
                if size and length != size:
                    raise SizeMismatchError(size, length)
                prefix.seek(0)
                try:
                    async with backend._client() as client:
                        await client.put_object(
                            Bucket=backend.bucket,
                            Key=key,
                            Body=prefix,
                            ContentType=content_type,
                            ContentLength=length,
                        )
                except Exception as exc:
                    raise StorageBackendError(f"S3 put_object failed: {exc}") from exc
                return
        prefix.seek(0)

        async def body() -> AsyncIterator[bytes]:
            while chunk := prefix.read(constants.DEFAULT_CHUNK_SIZE):
                yield chunk
            if tail is not None:
                for offset in range(0, len(tail), constants.DEFAULT_CHUNK_SIZE):
                    yield bytes(tail[offset : offset + constants.DEFAULT_CHUNK_SIZE])
            async for chunk in iterator:
                yield chunk

        await _multipart(backend, key, body(), content_type, size)


async def _multipart(backend: S3Backend, key, stream, content_type, size) -> None:
    part_size = upload_support.choose_part_size(size, backend.multipart_part_size_bytes)
    if part_size > constants.MAX_S3_PART_SIZE_BYTES:
        raise ValueError("S3 part size exceeds 5 GiB")
    upload_id = await backend.create_multipart(key, content_type)
    parts: list[Part] = []
    seen = 0
    try:
        with SpooledTemporaryFile(max_size=constants.SPOOL_MAX_SIZE_BYTES) as buf:
            async for chunk in stream:
                seen += len(chunk)
                if size and seen > size:
                    raise SizeMismatchError(size, seen)
                remaining = memoryview(chunk)
                while remaining:
                    take = min(len(remaining), part_size - buf.tell())
                    buf.write(remaining[:take])
                    remaining = remaining[take:]
                    if buf.tell() == part_size:
                        parts.append(await _send(backend, key, upload_id, parts, buf))
                        buf.seek(0)
                        buf.truncate()
            if size and seen != size:
                raise SizeMismatchError(size, seen)
            if buf.tell() or not parts:
                parts.append(await _send(backend, key, upload_id, parts, buf))
        await backend.complete_multipart(key, upload_id, parts)
    except BaseException:
        try:
            await backend.abort_multipart(key, upload_id)
        except BaseException:
            logger.exception("file_storage.server_upload_abort_failed key=%s", key)
        raise


async def _send(backend: S3Backend, key, upload_id, parts, buf) -> Part:
    number = len(parts) + 1
    if number > constants.MAX_UPLOAD_PARTS:
        raise ValueError("S3 upload exceeds maximum part count")
    length = buf.tell()
    buf.seek(0)
    try:
        async with backend._client() as client:
            result = await client.upload_part(
                Bucket=backend.bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=number,
                Body=buf,
                ContentLength=length,
            )
    except Exception as exc:
        raise StorageBackendError(f"S3 upload_part failed: {exc}") from exc
    return Part(no=number, etag=result["ETag"], size=length)
