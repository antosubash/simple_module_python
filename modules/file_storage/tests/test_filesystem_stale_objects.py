"""Filesystem reconciliation excludes in-progress uploads and runs off-thread."""

import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend


async def test_stale_objects_skip_parts_and_walk_in_worker(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path)
    old = backend._resolve("old/object.bin")
    fresh = backend._resolve("fresh/object.bin")
    short = backend._resolve("x")
    part = tmp_path / constants.FS_MULTIPART_DIR / ("a" * 32) / "1"
    for path in (old, fresh, short, part):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
        os.utime(path, (1, 1))
    os.utime(fresh, (200, 200))
    original_walk = os.walk
    caller_thread = threading.get_ident()
    walked = []

    def checked_walk(root):
        assert threading.get_ident() != caller_thread
        for entry in original_walk(root):
            walked.append(Path(entry[0]))
            yield entry

    monkeypatch.setattr(os, "walk", checked_walk)
    keys = [key async for key in backend.list_stale_objects(datetime.fromtimestamp(100, UTC))]
    assert set(keys) == {"old/object.bin"}
    assert not any(constants.FS_MULTIPART_DIR in path.parts for path in walked)
