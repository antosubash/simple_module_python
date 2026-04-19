"""Storage backend contract — extension point for new providers.

A storage provider is anything that satisfies :class:`StorageBackend`. Adding
a new provider (Azure Blob, GCS, R2 with custom auth, in-memory for tests)
means writing one module that implements this Protocol and self-registers via
:func:`file_storage.backends.register_backend`.

The Protocol is deliberately narrow: ``put``, ``get``, ``delete``, ``exists``,
plus capability flags so the service layer can dispatch (e.g. presigned-URL
download vs proxied stream) without inspecting backend identity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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
        """Yield the object's bytes in chunks. Raises :class:`StorageNotFoundError`."""

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
