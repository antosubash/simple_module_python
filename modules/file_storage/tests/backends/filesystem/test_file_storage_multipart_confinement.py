"""Multipart scratch files share the object store confinement (#1269)."""

from pathlib import Path

import pytest
from file_storage.backends import _fs_confined
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.contracts.service import Part, StorageBackendError

pytestmark = pytest.mark.skipif(
    not _fs_confined.CONFINED, reason="Requires descriptor-relative filesystem APIs."
)


@pytest.mark.parametrize("operation", ["create", "write", "list", "complete", "abort"])
async def test_multipart_symlink_outside_refused(tmp_path, chunks, operation):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    upload_id = "a" * 32
    parts = outside / upload_id
    parts.mkdir(parents=True)
    (parts / "1").write_bytes(b"secret")
    (parts / "1.etag").write_text("etag")
    (root / ".multipart").symlink_to(outside, target_is_directory=True)
    backend = FilesystemBackend(root)
    with pytest.raises(StorageBackendError):
        match operation:
            case "create":
                await backend.create_multipart("abc", "text/plain")
            case "write":
                await backend.write_part("abc", upload_id, 1, chunks(b"new"), max_bytes=3)
            case "list":
                await backend.list_parts("abc", upload_id)
            case "complete":
                await backend.complete_multipart(
                    "abc", upload_id, [Part(no=1, etag="etag", size=6)]
                )
            case "abort":
                await backend.abort_multipart("abc", upload_id)
    assert (parts / "1").read_bytes() == b"secret"
    assert sorted(p.name for p in outside.iterdir()) == [upload_id]


@pytest.mark.parametrize("link", ["upload", "part", "etag"])
async def test_nested_multipart_symlinks_refused(tmp_path, chunks, link):
    backend = FilesystemBackend(tmp_path / "root")
    upload_id = await backend.create_multipart("abc", "text/plain")
    directory = backend._parts_dir(upload_id)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "1").write_bytes(b"secret")
    if link == "upload":
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)
    else:
        (directory / "1").write_bytes(b"inside")
        target = directory / ("1" if link == "part" else "1.etag")
        target.unlink(missing_ok=True)
        target.symlink_to(outside / "1")
    with pytest.raises(StorageBackendError):
        await backend.list_parts("abc", upload_id)
    if link != "etag":
        with pytest.raises(StorageBackendError):
            await backend.complete_multipart("abc", upload_id, [Part(no=1, etag="", size=6)])
    assert (outside / "1").read_bytes() == b"secret"


async def test_multipart_roundtrip_and_limits(tmp_path, chunks):
    backend = FilesystemBackend(tmp_path)
    upload_id = await backend.create_multipart("ab/result", "text/plain")
    with pytest.raises(StorageBackendError):
        await backend.write_part("ab/result", upload_id, 1, chunks(b"too big"), max_bytes=2)
    assert await backend.list_parts("ab/result", upload_id) == []
    second = await backend.write_part("ab/result", upload_id, 2, chunks(b"world"), max_bytes=5)
    first = await backend.write_part("ab/result", upload_id, 1, chunks(b"hello "), max_bytes=6)
    assert await backend.list_parts("ab/result", upload_id) == [first, second]
    await backend.complete_multipart("ab/result", upload_id, [second, first])
    assert b"".join([c async for c in await backend.get("ab/result")]) == b"hello world"
    assert (await backend.head("ab/result")).size == 11
    assert not backend._parts_dir(upload_id).exists()
    await backend.abort_multipart("ab/result", upload_id)


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="Linux descriptor accounting.")
async def test_multipart_closes_descriptors_after_success_and_failures(tmp_path, chunks):
    backend = FilesystemBackend(tmp_path)
    before = len(list(Path("/proc/self/fd").iterdir()))
    for _ in range(3):
        upload_id = await backend.create_multipart("ab/file", "text/plain")
        with pytest.raises(StorageBackendError):
            await backend.write_part("ab/file", upload_id, 1, chunks(b"too big"), max_bytes=1)
        part = await backend.write_part("ab/file", upload_id, 1, chunks(b"ok"), max_bytes=2)
        with pytest.raises(StorageBackendError):
            await backend.complete_multipart("ab/file", upload_id, [Part(no=2, etag="", size=2)])
        assert await backend.list_parts("ab/file", upload_id) == [part]
        await backend.complete_multipart("ab/file", upload_id, [part])
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    assert not list(tmp_path.rglob("*.tmp"))


async def test_multipart_write_keeps_open_directory_after_scratch_rename(
    tmp_path, monkeypatch, chunks
):
    from file_storage.backends._fs_confined import Directory

    backend = FilesystemBackend(tmp_path / "root")
    upload_id = await backend.create_multipart("abc", "text/plain")
    scratch = backend.root / ".multipart"
    moved = backend.root / "moved"
    outside = tmp_path / "outside"
    (outside / upload_id).mkdir(parents=True)
    (outside / upload_id / "1").write_bytes(b"secret")
    original = Directory.open

    def swap(parent, name, mode="rb"):
        if not moved.exists():
            scratch.rename(moved)
            scratch.symlink_to(outside, target_is_directory=True)
        return original(parent, name, mode)

    monkeypatch.setattr(Directory, "open", swap)
    await backend.write_part("abc", upload_id, 1, chunks(b"new"), max_bytes=3)
    assert (moved / upload_id / "1").read_bytes() == b"new"
    assert (outside / upload_id / "1").read_bytes() == b"secret"
    assert sorted(p.name for p in (outside / upload_id).iterdir()) == ["1"]
