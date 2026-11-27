"""Directory swaps must never redirect object I/O outside storage (#1269)."""

import asyncio
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from file_storage.backends import _fs_confined
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.contracts.service import StorageBackendError, StorageNotFoundError

pytestmark = pytest.mark.skipif(
    not _fs_confined.CONFINED, reason="Requires descriptor-relative filesystem APIs."
)


@pytest.mark.parametrize("operation", ["get", "range", "put", "exists", "head", "delete"])
async def test_shard_swap_after_validation(tmp_path, monkeypatch, chunks, operation):
    root, outside = tmp_path / "root", tmp_path / "outside"
    shard = root / "ab"
    shard.mkdir(parents=True)
    outside.mkdir()
    if operation != "exists":
        (shard / "abc").write_bytes(b"inside")
    (outside / "abc").write_bytes(b"outside-secret")
    backend = FilesystemBackend(root)
    resolve = backend._resolve
    swapped = False

    def swap(key):
        nonlocal swapped
        path = resolve(key)
        if not swapped:
            shard.rename(root / "saved")
            shard.symlink_to(outside, target_is_directory=True)
            swapped = True
        return path

    monkeypatch.setattr(backend, "_resolve", swap)
    try:
        match operation:
            case "get" | "range":
                body = (
                    await backend.get("abc")
                    if operation == "get"
                    else await backend.get_range("abc", 0, 2)
                )
                assert b"".join([chunk async for chunk in body]) == (
                    b"inside" if operation == "get" else b"ins"
                )
            case "put":
                await backend.put("abc", chunks(b"new"), content_type="text/plain", size=3)
            case "exists":
                assert await backend.exists("abc") is False
            case "head":
                assert (await backend.head("abc")).size == 6
            case "delete":
                await backend.delete("abc")
    except StorageBackendError:
        pass  # Refusing the replaced directory is also safe.
    assert swapped
    assert (outside / "abc").read_bytes() == b"outside-secret"
    assert sorted(p.name for p in outside.iterdir()) == ["abc"]


@pytest.mark.parametrize("ranged", [False, True])
async def test_read_holds_open_file_before_stream_consumption(tmp_path, ranged):
    backend = FilesystemBackend(tmp_path)
    path = backend._resolve("abc")
    path.parent.mkdir()
    path.write_bytes(b"inside")
    body = await backend.get_range("abc", 1, 3) if ranged else await backend.get("abc")
    path.rename(path.with_suffix(".old"))
    path.write_bytes(b"replacement")
    assert b"".join([chunk async for chunk in body]) == (b"nsi" if ranged else b"inside")


async def test_stale_listing_does_not_follow_directory_swapped_during_walk(tmp_path, monkeypatch):
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "ab" / "ab").mkdir(parents=True)
    (outside / "ab").mkdir(parents=True)
    (outside / "ab" / "secret").write_bytes(b"outside")
    os.utime(outside / "ab" / "secret", (1, 1))
    backend = FilesystemBackend(root)
    original_listdir = os.listdir
    original_walk = os.walk
    swapped = False

    def swap():
        nonlocal swapped
        if not swapped:
            (root / "ab").rename(root / "saved")
            (root / "ab").symlink_to(outside, target_is_directory=True)
            swapped = True

    def listdir(path):
        names = original_listdir(path)
        swap()
        return names

    def walk(path):
        for entry in original_walk(path):
            swap()
            yield entry

    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(os, "walk", walk)
    assert [key async for key in backend.list_stale_objects(datetime.fromtimestamp(100, UTC))] == []


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="Linux descriptor accounting.")
async def test_file_descriptors_closed_on_success_failure_and_partial_read(tmp_path, chunks):
    backend = FilesystemBackend(tmp_path)
    before = len(list(Path("/proc/self/fd").iterdir()))
    for _ in range(4):
        await backend.put("ab/file", chunks(b"payload"), content_type="text/plain", size=7)
        body = await backend.get("ab/file")
        await anext(body)
        await body.aclose()
        unopened = await backend.get("ab/file")
        await unopened.aclose()
        with pytest.raises(StorageNotFoundError):
            await backend.get("ab/missing")

        async def broken():
            yield b"partial"
            raise ValueError("failed stream")

        with pytest.raises(ValueError, match="failed stream"):
            await backend.put("ab/file", broken(), content_type="text/plain", size=0)
        assert b"".join([chunk async for chunk in await backend.get("ab/file")]) == b"payload"
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("operation", ["get", "put"])
async def test_opened_parent_stays_anchored_during_rename(tmp_path, monkeypatch, chunks, operation):
    from file_storage.backends._fs_confined import Directory

    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "ab").mkdir(parents=True)
    outside.mkdir()
    (root / "ab" / "abc").write_bytes(b"inside")
    (outside / "abc").write_bytes(b"outside")
    backend = FilesystemBackend(root)
    opened = Directory.open
    swapped = False

    def swap(parent, name, mode="rb"):
        nonlocal swapped
        if not swapped:
            (root / "ab").rename(root / "moved")
            (root / "ab").symlink_to(outside, target_is_directory=True)
            swapped = True
        return opened(parent, name, mode)

    monkeypatch.setattr(Directory, "open", swap)
    if operation == "get":
        assert b"".join([c async for c in await backend.get("abc")]) == b"inside"
    else:
        await backend.put("abc", chunks(b"new"), content_type="text/plain", size=3)
        assert (root / "moved" / "abc").read_bytes() == b"new"
    assert swapped
    assert (outside / "abc").read_bytes() == b"outside"
    assert sorted(p.name for p in outside.iterdir()) == ["abc"]


@pytest.mark.parametrize("operation", ["get", "range", "exists", "head"])
async def test_leaf_symlink_swapped_at_io_is_refused(tmp_path, monkeypatch, operation):
    from file_storage.backends._fs_confined import Directory

    backend = FilesystemBackend(tmp_path / "root")
    path = backend._resolve("abc")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.write_bytes(b"secret")
    method = "open" if operation in {"get", "range"} else "stat"
    original = getattr(Directory, method)

    def swap(parent, name, *args):
        path.unlink()
        path.symlink_to(outside)
        return original(parent, name, *args)

    monkeypatch.setattr(Directory, method, swap)
    with pytest.raises(StorageBackendError):
        if operation == "get":
            await backend.get("abc")
        elif operation == "range":
            await backend.get_range("abc", 0, 2)
        else:
            await getattr(backend, operation)("abc")
    assert outside.read_bytes() == b"secret"


async def test_cancelled_open_finishes_before_descriptor_cleanup(tmp_path, monkeypatch, chunks):
    from file_storage.backends._fs_confined import Directory

    backend = FilesystemBackend(tmp_path)
    entered, release = threading.Event(), threading.Event()
    opened = []
    original = Directory.open

    def slow_open(parent, name, mode="rb"):
        file = original(parent, name, mode)
        opened.append(file)
        entered.set()
        assert release.wait(3)
        return file

    monkeypatch.setattr(Directory, "open", slow_open)
    task = asyncio.create_task(
        backend.put("abc", chunks(b"data"), content_type="text/plain", size=4)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.to_thread(lambda: None)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert opened and all(file.closed for file in opened)
    assert not list(tmp_path.rglob("*.tmp"))


async def test_stale_metadata_stays_confined_after_validation(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "root")
    inside = backend._resolve("ab/file")
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"fresh")
    os.utime(inside, (200, 200))
    outside = tmp_path / "outside"
    (outside / "ab").mkdir(parents=True)
    (outside / "ab" / "file").write_bytes(b"old outside")
    os.utime(outside / "ab" / "file", (1, 1))
    original_stat, original_is_file = os.stat, Path.is_file
    swapped = False

    def swap():
        nonlocal swapped
        if not swapped:
            (backend.root / "ab").rename(backend.root / "moved")
            (backend.root / "ab").symlink_to(outside, target_is_directory=True)
            swapped = True

    def stat(path, *args, **kwargs):
        if path == "file" and kwargs.get("dir_fd") is not None:
            swap()
        return original_stat(path, *args, **kwargs)

    def is_file(path):
        if path == inside:
            swap()  # The old path-based scanner has finished both path checks.
        return original_is_file(path)

    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(Path, "is_file", is_file)
    assert [k async for k in backend.list_stale_objects(datetime.fromtimestamp(100, UTC))] == []
    assert swapped
