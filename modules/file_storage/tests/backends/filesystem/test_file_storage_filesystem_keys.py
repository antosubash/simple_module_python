"""Filesystem key confinement, including the shard and existing symlinks (#1266)."""

import os
from pathlib import Path

import pytest
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.contracts.service import StorageBackendError
from file_storage.files.service import generate_key


@pytest.mark.parametrize(
    "key",
    [
        "",
        ".",
        "..",
        "..abc",
        "a/../../x",
        "/etc/passwd",
        "//server/share/file",
        "C:/escape",
        "C:escape",
        "c:/escape",
        "a\\b",
        "C:\\escape",
        "a\x00b",
    ],
)
def test_invalid_keys_rejected(tmp_path, key):
    with pytest.raises(StorageBackendError):
        FilesystemBackend(tmp_path)._resolve(key)


@pytest.mark.skipif(os.name == "nt", reason="Windows paths use UTF-16 instead of UTF-8.")
@pytest.mark.parametrize("key", ["ab\ud800", "ab\udfff"])
def test_unencodable_keys_raise_backend_error(tmp_path, key):
    with pytest.raises(StorageBackendError):
        FilesystemBackend(tmp_path)._resolve(key)
    assert list(tmp_path.iterdir()) == []


def test_parent_shard_rejected_even_if_symlink_points_back_inside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "..abc").symlink_to(root / "object.bin")

    with pytest.raises(StorageBackendError):
        FilesystemBackend(root)._resolve("..abc")


@pytest.mark.parametrize("link_at", ["shard", "file"])
def test_symlink_escape_rejected(tmp_path, link_at):
    root = tmp_path / "root"
    outside = tmp_path / "root-other"
    outside.mkdir()
    root.mkdir()
    if link_at == "shard":
        (root / "ab").symlink_to(outside, target_is_directory=True)
    else:
        (root / "ab").mkdir()
        (root / "ab" / "abc").symlink_to(outside / "object.bin")

    with pytest.raises(StorageBackendError):
        FilesystemBackend(root)._resolve("abc")


def test_symlink_loop_raises_backend_error(tmp_path):
    (tmp_path / "ab").symlink_to(tmp_path / "ab", target_is_directory=True)
    with pytest.raises(StorageBackendError):
        FilesystemBackend(tmp_path)._resolve("abc")


@pytest.mark.parametrize(
    ("key", "relative"),
    [
        ("ab/file.bin", "ab/ab/file.bin"),
        ("2026/04/19/abc123.png", "20/2026/04/19/abc123.png"),
        ("tenant/2026/11/27/abc.thumb.webp", "te/tenant/2026/11/27/abc.thumb.webp"),
        ("abc", "ab/abc"),
        ("x", "_/x"),
        (".abc", ".a/.abc"),
    ],
)
def test_existing_key_paths_unchanged(tmp_path, key, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing")

    resolved = FilesystemBackend(tmp_path)._resolve(key)
    assert resolved == path
    assert resolved.read_bytes() == b"existing"


def test_generated_key_path_unchanged_with_symlinked_relative_root(tmp_path, monkeypatch):
    root = tmp_path / "actual"
    root.mkdir()
    (tmp_path / "storage").symlink_to(root, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    key = generate_key("acme", "photo.png")

    assert FilesystemBackend(Path("storage"))._resolve(key) == root / "ac" / key


@pytest.mark.parametrize("key", ["..abc", "C:/escape"])
@pytest.mark.parametrize(
    "method", ["put", "get", "get_range", "exists", "delete", "head", "create", "complete"]
)
async def test_key_operations_reject_invalid_keys(tmp_path, key, method):
    backend = FilesystemBackend(tmp_path)

    async def stream():
        yield b"x"

    with pytest.raises(StorageBackendError):
        match method:
            case "put":
                await backend.put(key, stream(), content_type="text/plain", size=1)
            case "get":
                await backend.get(key)
            case "get_range":
                await backend.get_range(key, 0, 0)
            case "exists":
                await backend.exists(key)
            case "delete":
                await backend.delete(key)
            case "head":
                await backend.head(key)
            case "create":
                await backend.create_multipart(key, "text/plain")
            case "complete":
                await backend.complete_multipart(key, "a" * 32, [])
    assert list(tmp_path.iterdir()) == []


def test_stale_listing_skips_unsafe_keys_and_external_symlinks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    paths = [
        root / "ab" / "ab" / "safe.bin",
        root / "C:" / "C:" / "unsafe.bin",
        root / "zz" / "ab" / "wrong-shard.bin",
        root / "ab" / "ab" / "external.bin",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "external.bin":
            path.symlink_to(outside)
        else:
            path.write_bytes(b"inside")
        os.utime(path, (1, 1))

    assert FilesystemBackend(root)._collect_stale_objects(100) == ["ab/safe.bin"]
