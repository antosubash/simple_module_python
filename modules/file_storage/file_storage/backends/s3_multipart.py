"""Multipart-upload half of the S3 backend (#454).

Parts go from the browser straight to the bucket through presigned
``upload_part`` URLs, so a multi-GB file never crosses the app server. URLs
are presigned against the *browser-facing* endpoint (``s3_public_endpoint_url``
when set): a SigV4 signature covers the host, so one signed for an internal
hostname would be rejected when the browser sent it to the public one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from file_storage.contracts.service import (
    NotSupportedError,
    ObjectInfo,
    Part,
    StorageBackendError,
    StorageNotFoundError,
)

_MAX_LIST_PAGE = 1000


class S3MultipartMixin:
    """Mixed into :class:`~file_storage.backends.s3.S3Backend`."""

    supports_direct_upload = True
    bucket: str
    client_kwargs: dict[str, Any]
    public_endpoint_url: str

    def _client(self):  # provided by the concrete backend
        raise NotImplementedError

    def _presign_client(self):
        if not self.public_endpoint_url:
            return self._client()
        return self._session.client(  # type: ignore[attr-defined]
            "s3", **{**self.client_kwargs, "endpoint_url": self.public_endpoint_url}
        )

    async def create_multipart(self, key: str, content_type: str) -> str:
        try:
            async with self._client() as client:
                resp = await client.create_multipart_upload(
                    Bucket=self.bucket, Key=key, ContentType=content_type
                )
            return resp["UploadId"]
        except Exception as exc:
            raise StorageBackendError(f"S3 create_multipart_upload failed: {exc}") from exc

    async def presign_part(self, key: str, upload_id: str, part_no: int, ttl: int) -> str:
        return await self._presign(
            "upload_part",
            {"Bucket": self.bucket, "Key": key, "UploadId": upload_id, "PartNumber": part_no},
            ttl,
        )

    async def presigned_put_url(self, key: str, ttl: int, content_type: str) -> str:
        return await self._presign(
            "put_object", {"Bucket": self.bucket, "Key": key, "ContentType": content_type}, ttl
        )

    async def _presign(self, operation: str, params: dict[str, Any], ttl: int) -> str:
        try:
            async with self._presign_client() as client:
                return await client.generate_presigned_url(operation, Params=params, ExpiresIn=ttl)
        except Exception as exc:
            raise StorageBackendError(f"presign failed: {exc}") from exc

    async def write_part(self, key, upload_id, part_no, stream, *, max_bytes: int) -> Part:
        raise NotSupportedError("S3 parts are uploaded directly with presigned URLs.")

    async def list_parts(self, key: str, upload_id: str) -> list[Part]:
        parts: list[Part] = []
        marker = 0
        try:
            async with self._client() as client:
                while True:
                    resp = await client.list_parts(
                        Bucket=self.bucket,
                        Key=key,
                        UploadId=upload_id,
                        MaxParts=_MAX_LIST_PAGE,
                        PartNumberMarker=marker,
                    )
                    parts.extend(
                        Part(no=p["PartNumber"], etag=p["ETag"], size=p["Size"])
                        for p in resp.get("Parts", [])
                    )
                    if not resp.get("IsTruncated"):
                        return sorted(parts, key=lambda p: p.no)
                    marker = resp["NextPartNumberMarker"]
        except Exception as exc:
            if _is_no_such_upload(exc):
                raise StorageNotFoundError(upload_id) from exc
            raise StorageBackendError(f"S3 list_parts failed: {exc}") from exc

    async def complete_multipart(self, key: str, upload_id: str, parts: list[Part]) -> None:
        try:
            async with self._client() as client:
                await client.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={
                        "Parts": [
                            {"PartNumber": p.no, "ETag": p.etag}
                            for p in sorted(parts, key=lambda p: p.no)
                        ]
                    },
                )
        except Exception as exc:
            raise StorageBackendError(f"S3 complete_multipart_upload failed: {exc}") from exc

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            async with self._client() as client:
                await client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except Exception as exc:
            if _is_no_such_upload(exc):
                return
            raise StorageBackendError(f"S3 abort_multipart_upload failed: {exc}") from exc

    async def head(self, key: str) -> ObjectInfo:
        try:
            async with self._client() as client:
                resp = await client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_no_such_key(exc):
                raise StorageNotFoundError(key) from exc
            raise StorageBackendError(f"S3 head_object failed: {exc}") from exc
        return ObjectInfo(size=resp["ContentLength"], etag=resp.get("ETag"))

    async def list_stale_multipart(self, older_than: timedelta) -> list[tuple[str, str]]:
        """``(key, upload_id)`` of in-progress uploads started before ``now - older_than``.

        For the janitor: a browser that vanished mid-upload leaves parts that
        S3 bills for until someone aborts the upload.
        """
        cutoff = datetime.now(UTC) - older_than
        found: list[tuple[str, str]] = []
        key_marker = upload_marker = None
        try:
            async with self._client() as client:
                while True:
                    kwargs: dict[str, Any] = {"Bucket": self.bucket}
                    if key_marker:
                        kwargs["KeyMarker"] = key_marker
                        kwargs["UploadIdMarker"] = upload_marker
                    resp = await client.list_multipart_uploads(**kwargs)
                    found.extend(
                        (u["Key"], u["UploadId"])
                        for u in resp.get("Uploads", [])
                        if u["Initiated"] < cutoff
                    )
                    if not resp.get("IsTruncated"):
                        return found
                    key_marker = resp.get("NextKeyMarker")
                    upload_marker = resp.get("NextUploadIdMarker")
        except Exception as exc:
            raise StorageBackendError(f"S3 list_multipart_uploads failed: {exc}") from exc


def _code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def _is_no_such_upload(exc: Exception) -> bool:
    return _code(exc) == "NoSuchUpload"


def _is_no_such_key(exc: Exception) -> bool:
    return _code(exc) in {"NoSuchKey", "404", "NotFound"}
