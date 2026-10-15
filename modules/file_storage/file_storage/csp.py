"""CSP ``connect-src`` origins for direct-to-bucket uploads (#454)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from file_storage import constants

if TYPE_CHECKING:
    from fastapi import FastAPI

    from file_storage.settings import FileStorageSettings


def s3_connect_origins(settings: FileStorageSettings) -> list[str]:
    """Origins a browser PUTs S3 parts to; empty unless the backend is S3.

    A custom endpoint (MinIO, R2) contributes its own origin, taken from
    ``s3_public_endpoint_url`` when set. With none, botocore presigns virtual-
    hosted AWS URLs, so the bucket's own hostnames are allowed instead.
    """
    if settings.backend != constants.BackendId.S3:
        return []
    endpoint = settings.presign_endpoint_url()
    if endpoint:
        parts = urlsplit(endpoint)
        return [f"{parts.scheme}://{parts.netloc}"] if parts.scheme and parts.netloc else []
    bucket = settings.s3_bucket
    return [
        f"https://{bucket}.s3.{settings.s3_region}.amazonaws.com",
        f"https://{bucket}.s3.amazonaws.com",
    ]


def connect_src_provider(app: FastAPI) -> list[tuple[str, str]]:
    services = getattr(app.state, "file_storage", None)
    if services is None:
        return []
    return [("connect-src", origin) for origin in s3_connect_origins(services.settings)]
