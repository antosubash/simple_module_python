"""Module-scoped state container.

Stored as ``app.state.file_storage`` by
:meth:`FileStorageModule.register_settings`.

Holds the resolved :class:`StorageBackend` so endpoints don't reconstruct it
per request — provider handles (S3 client sessions, open file descriptors)
are pooled inside the backend instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend
    from file_storage.settings import FileStorageSettings


@dataclass
class FileStorageServices:
    """file_storage module singletons. Single slot at ``app.state.file_storage``."""

    settings: FileStorageSettings
    backend: StorageBackend
