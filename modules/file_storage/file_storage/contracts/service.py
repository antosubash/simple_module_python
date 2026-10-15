"""Storage backend contract — extension point for new providers.

A storage provider is anything that satisfies :class:`StorageBackend`. Adding
a new provider (Azure Blob, GCS, R2 with custom auth, in-memory for tests)
means writing one module that implements this Protocol and self-registers via
:func:`file_storage.backends.register_backend`.

The Protocol is deliberately narrow: ``put``, ``get``, ``get_range``,
``delete``, ``exists``, plus capability flags so the service layer can dispatch (e.g. presigned-URL
download vs proxied stream) without inspecting backend identity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class StorageError(Exception):
    """Base class for all storage backend errors."""


class StorageNotFoundError(StorageError):
    """Raised when an object key does not exist in the backend."""


class StorageBackendError(StorageError):
    """Raised when the backend itself fails (network, IO, auth)."""


class NotSupportedError(StorageError):
    """Raised when a backend does not implement an optional capability."""


class ConfigurationError(StorageError):
    """Raised at backend construction when required config is missing."""


@runtime_checkable
class StorageBackend(Protocol):
    """Async object storage abstraction.

    Implementations must be safe to share across requests — they're held as
    a singleton on ``app.state.file_storage.backend``.
    """

    backend_id: str
    """Stable identifier matching the registry key (e.g. ``"filesystem"``)."""

    supports_presigned_url: bool
    """Whether :meth:`presigned_get_url` returns a usable URL.

    The download endpoint reads this flag to choose between proxying bytes
    and issuing a 302 redirect — no `if backend == "s3"` branching.
    """

    async def put(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        *,
        content_type: str,
        size: int,
    ) -> None:
        """Persist ``stream`` under ``key``. ``size`` is the total byte count."""

    async def get(self, key: str) -> AsyncIterator[bytes]:
        """Return an iterator over the object's bytes in bounded chunks.

        Awaiting the call opens the object, so a missing key raises
        :class:`StorageNotFoundError` here rather than mid-stream. The object
        must be streamed, never buffered whole: files can be many GB.
        """

    async def get_range(self, key: str, start: int, end: int) -> AsyncIterator[bytes]:
        """Like :meth:`get`, for bytes ``start`` through ``end`` *inclusive*.

        HTTP ``Range`` semantics: ``get_range(k, 0, 0)`` is the first byte. The
        caller has already validated ``0 <= start <= end < size``; backends need
        not re-check against the object's size. Optional for third-party
        backends — without it the download endpoints ignore ``Range`` and send
        the whole object.
        """

    async def delete(self, key: str) -> None:
        """Remove the object at ``key``. No-op if absent."""

    async def exists(self, key: str) -> bool:
        """Return whether an object exists at ``key``."""

    async def presigned_get_url(self, key: str, ttl_seconds: int) -> str:
        """Return a short-lived URL the client can fetch directly.

        Implementations without presigned-URL support must raise
        :class:`NotSupportedError`. The endpoint will not call this on
        backends with ``supports_presigned_url=False``.
        """


@dataclass(frozen=True)
class Part:
    """One uploaded part of a multipart upload, as the backend reports it."""

    no: int
    etag: str
    size: int


@dataclass(frozen=True)
class ObjectInfo:
    """What :meth:`DirectUploadBackend.head` knows about a stored object."""

    size: int
    etag: str | None = None


class DirectUploadBackend(Protocol):
    """Optional capability: resumable multipart uploads (#454).

    Backends advertise it with ``supports_direct_upload = True``; the service
    reads the flag with ``getattr(..., False)`` so third-party backends written
    before this existed keep working. The backend's :meth:`list_parts` is the
    source of truth for what has been uploaded — the database never mirrors it.

    A backend that can mint URLs the browser PUTs to directly (S3) implements
    :meth:`presign_part`; one that cannot (filesystem) raises
    :class:`NotSupportedError` from it, and parts travel through the app
    instead, landing in :meth:`write_part`.
    """

    supports_direct_upload: bool

    async def create_multipart(self, key: str, content_type: str) -> str:
        """Start an upload; return the backend's upload id."""

    async def presign_part(
        self, key: str, upload_id: str, part_no: int, ttl: int, size: int | None = None
    ) -> str:
        """URL the browser PUTs one part to, length-bound to ``size`` where the store can.

        :class:`NotSupportedError` if the backend has no such URLs.
        """

    async def write_part(
        self,
        key: str,
        upload_id: str,
        part_no: int,
        stream: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> Part:
        """Store one part streamed through the app. :class:`NotSupportedError` if presigned."""

    async def list_parts(self, key: str, upload_id: str) -> list[Part]:
        """Parts received so far, ascending by number."""

    async def complete_multipart(self, key: str, upload_id: str, parts: list[Part]) -> None:
        """Assemble ``parts`` into the object at ``key``."""

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        """Discard the upload and its parts. No-op if already gone."""

    async def presigned_put_url(self, key: str, ttl: int, content_type: str) -> str:
        """URL for a single-request direct PUT. :class:`NotSupportedError` if none."""

    async def head(self, key: str) -> ObjectInfo:
        """Size of the stored object; :class:`StorageNotFoundError` if absent."""
