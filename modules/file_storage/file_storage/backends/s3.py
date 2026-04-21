"""S3-compatible storage backend (AWS S3, MinIO, Cloudflare R2, ...).

``aioboto3`` is imported lazily at backend construction so the module loads
even when the optional S3 extra isn't installed; the failure mode is a clear
:class:`ConfigurationError` at boot rather than a confusing import error.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Any

from file_storage import constants
from file_storage.backends import register_backend
from file_storage.contracts.service import (
    ConfigurationError,
    StorageBackendError,
    StorageNotFoundError,
)
from file_storage.settings import FileStorageSettings

if TYPE_CHECKING:
    pass


class S3Backend:
    """S3-compatible object storage.

    Each operation opens a fresh ``aioboto3`` client context (cheap; the
    underlying ``aiobotocore`` session is reused via ``self._session``). We
    deliberately do not hold one long-lived client across requests because
    aioboto3 client contexts are per-event-loop and tests run multiple loops.
    """

    backend_id = constants.BackendId.S3
    supports_presigned_url = True

    def __init__(self, *, bucket: str, region: str, client_kwargs: dict[str, Any]) -> None:
        try:
            import aioboto3
        except ImportError as exc:
            raise ConfigurationError(
                "S3 backend requires the 'aioboto3' package. "
                "Install with: uv add --optional s3 aioboto3"
            ) from exc
        self._aioboto3 = aioboto3
        self._session = aioboto3.Session()
        self.bucket = bucket
        self.region = region
        self.client_kwargs = client_kwargs

    def _client(self):
        return self._session.client("s3", **self.client_kwargs)

    async def put(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        *,
        content_type: str,
        size: int,
    ) -> None:
        # Spool to memory up to SPOOL_MAX_SIZE_BYTES, then to a temp file.
        # put_object needs a seekable file-like; multipart upload would be
        # the next step for very large files (deferred to v2).
        with SpooledTemporaryFile(max_size=constants.SPOOL_MAX_SIZE_BYTES) as buf:
            async for chunk in stream:
                buf.write(chunk)
            length = buf.tell()
            buf.seek(0)
            try:
                async with self._client() as client:
                    await client.put_object(
                        Bucket=self.bucket,
                        Key=key,
                        Body=buf,
                        ContentType=content_type,
                        ContentLength=length,
                    )
            except Exception as exc:
                raise StorageBackendError(f"S3 put_object failed: {exc}") from exc

    async def get(self, key: str) -> AsyncIterator[bytes]:
        try:
            async with self._client() as client:
                resp = await client.get_object(Bucket=self.bucket, Key=key)
                # ``Body.read()`` works uniformly across aioboto3 (real) and
                # moto's patched aiobotocore (tests); ``iter_chunks`` is sync
                # under moto, breaking ``async for``.
                data = await resp["Body"].read()
        except Exception as exc:
            if _is_not_found(exc):
                raise StorageNotFoundError(key) from exc
            raise StorageBackendError(f"S3 get_object failed: {exc}") from exc

        for offset in range(0, len(data), constants.DEFAULT_CHUNK_SIZE):
            yield data[offset : offset + constants.DEFAULT_CHUNK_SIZE]

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as client:
                await client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageBackendError(f"S3 delete_object failed: {exc}") from exc

    async def exists(self, key: str) -> bool:
        try:
            async with self._client() as client:
                await client.head_object(Bucket=self.bucket, Key=key)
                return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise StorageBackendError(f"S3 head_object failed: {exc}") from exc

    async def presigned_get_url(self, key: str, ttl_seconds: int) -> str:
        try:
            async with self._client() as client:
                return await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=ttl_seconds,
                )
        except Exception as exc:
            raise StorageBackendError(f"presign failed: {exc}") from exc


def _is_not_found(exc: Exception) -> bool:
    """Detect a 404 from botocore's heterogeneous error shapes."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return True
    return getattr(exc, "__class__", type(exc)).__name__ in {
        "NoSuchKey",
        "ClientError",
    } and "404" in str(exc)


@register_backend(constants.BackendId.S3)
def _build(settings: FileStorageSettings) -> S3Backend:
    if not settings.s3_bucket or not settings.s3_region:
        raise ConfigurationError("S3 backend requires s3_bucket and s3_region.")
    client_kwargs: dict[str, Any] = {"region_name": settings.s3_region}
    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_access_key_id and settings.s3_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    return S3Backend(
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        client_kwargs=client_kwargs,
    )
