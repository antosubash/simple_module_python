"""file_storage contracts — public interface for other modules."""

from __future__ import annotations

from contextlib import AbstractContextManager
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO
from uuid import UUID

from file_storage.contracts.events import FileDeleted, FileUploaded
from file_storage.contracts.schemas import StoredFileListOut, StoredFileOut
from file_storage.contracts.service import (
    ConfigurationError,
    DirectUploadBackend,
    NotSupportedError,
    ObjectInfo,
    Part,
    StorageBackend,
    StorageBackendError,
    StorageError,
    StorageNotFoundError,
)
from file_storage.models import StoredFile

if TYPE_CHECKING:
    from file_storage.files.service import FileStorageService as FileStorageService
    from file_storage.web.deps import get_file_storage_service as get_file_storage_service

__all__ = [
    "ConfigurationError",
    "DirectUploadBackend",
    "FileDeleted",
    "FileStorageService",
    "FileUploaded",
    "NotSupportedError",
    "ObjectInfo",
    "Part",
    "StorageBackend",
    "StorageBackendError",
    "StorageError",
    "StorageNotFoundError",
    "StoredFile",
    "StoredFileListOut",
    "StoredFileOut",
    "get_file_storage_service",
    "open_local",
    "presigned_url",
    "store_path",
]


def __getattr__(name: str):
    # Service and dependency imports also load contracts submodules.
    if name == "FileStorageService":
        from file_storage.files.service import FileStorageService

        return FileStorageService
    if name == "get_file_storage_service":
        from file_storage.web.deps import get_file_storage_service

        return get_file_storage_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def store_path(
    source: str | PathLike[str] | BinaryIO,
    *,
    filename: str | None = None,
    content_type: str = "application/octet-stream",
    public: bool = False,
) -> StoredFileOut:
    """Store a path or stream in the caller's tenant, in an independent transaction."""
    from file_storage.core.worker import store_path as store

    return store(source, filename=filename, content_type=content_type, public=public)


def open_local(file_id: UUID) -> AbstractContextManager[Path]:
    """Download to a private local path for the lifetime of this context."""
    from file_storage.core.worker import open_local as local

    return local(file_id)


def presigned_url(file_id: UUID, *, ttl_seconds: int | None = None) -> str:
    """Return a scoped download URL; unsupported backends raise NotSupportedError."""
    from file_storage.core.worker import presigned_url as sign

    return sign(file_id, ttl_seconds=ttl_seconds)
