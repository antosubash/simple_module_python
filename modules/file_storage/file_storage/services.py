"""Module-scoped state container.

Stored as ``app.state.file_storage`` by
:meth:`FileStorageModule.register_settings`.

Holds the resolved :class:`StorageBackend` so endpoints don't reconstruct it
per request — provider handles (S3 client sessions, open file descriptors)
are pooled inside the backend instance. ``backend`` is populated in
``on_startup`` (after settings have been hydrated from the DB), so it's
optional at construction time.

It also holds the browse screen's :class:`AggregateCache`. Per-app rather than
per-process for the same reason the backend is: a process running two apps must
not answer one app's request out of the other's database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from file_storage.aggregates import AggregateCache

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend
    from file_storage.settings import FileStorageSettings


@dataclass
class FileStorageServices:
    """file_storage module singletons. Single slot at ``app.state.file_storage``."""

    settings: FileStorageSettings
    backend: StorageBackend | None = None
    aggregates: AggregateCache = field(default_factory=AggregateCache)
