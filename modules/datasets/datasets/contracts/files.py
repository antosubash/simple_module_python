"""Public-facing value types for dataset file access.

Consumers that depend on the Datasets module import ``DatasetFile`` rather
than the private ``Dataset`` SQLModel table. It carries enough to stream
bytes, mmap, or hand off to a GIS library without a second round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from datasets.contracts.schemas import DatasetOut


@dataclass(frozen=True)
class DatasetFile:
    """Read-only handle to a stored dataset file.

    ``path`` points at the on-disk file for the local FS backend. If the
    project later swaps ``LocalDatasetStorage`` for an S3 implementation,
    ``path`` will become a ``Path`` to a temp file fetched on demand and
    cleaned up when the handle is garbage-collected — callers should treat
    it as opaque and prefer ``open()`` over passing it around.
    """

    metadata: DatasetOut
    path: Path
    original_filename: str
    mime_type: str | None

    def open(self, mode: str = "rb"):
        """Open the underlying file. Defaults to binary read."""
        return self.path.open(mode)

    @property
    def exists(self) -> bool:
        return self.path.exists()
