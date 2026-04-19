"""Local-filesystem storage for uploaded GIS dataset files.

Designed as a thin abstraction so the service never touches the filesystem
directly. A future S3 backend can implement the same surface without
disturbing callers.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import BinaryIO

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Return a filename safe to write under storage_dir.

    Strips path separators and collapses anything outside ``[A-Za-z0-9._-]``
    to underscores, defending against directory traversal in user-supplied
    upload names.
    """
    base = Path(name).name or "upload.bin"
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._") or "upload.bin"
    return cleaned[:200]


class LocalDatasetStorage:
    """Stores each dataset's file under ``<root>/<dataset_id>/<filename>``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def is_writable(self) -> bool:
        if not self.root.exists() or not self.root.is_dir():
            return False
        probe = self.root / ".write_probe"
        try:
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            return False
        return True

    def key_for(self, dataset_id: int, filename: str) -> str:
        return f"{dataset_id}/{safe_filename(filename)}"

    def absolute(self, key: str) -> Path:
        return self.root / key

    def write_stream(self, key: str, source: BinaryIO, *, chunk_size: int = 1024 * 1024) -> int:
        """Stream ``source`` into ``key``. Returns the number of bytes written."""
        target = self.absolute(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        with target.open("wb") as fp:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                fp.write(chunk)
                bytes_written += len(chunk)
        return bytes_written

    def open_read(self, key: str) -> BinaryIO:
        return self.absolute(key).open("rb")

    def delete(self, key: str) -> None:
        path = self.absolute(key)
        if not path.exists():
            return
        # Remove the dataset's directory entirely so we don't leave empty
        # parents around after the file goes; the layout is one dir per id.
        parent = path.parent
        if parent != self.root and parent.is_dir():
            shutil.rmtree(parent, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
