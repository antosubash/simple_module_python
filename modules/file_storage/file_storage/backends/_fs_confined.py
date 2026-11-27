"""Descriptor-relative filesystem I/O; path fallback where dir_fd is unavailable."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import stat
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from typing import IO, Literal

from file_storage.backends._io import _io
from file_storage.contracts.service import StorageBackendError
from file_storage.core import constants

# replace uses rename's dir_fd implementation, but is not in supports_dir_fd.
CONFINED = (
    os.name != "nt"
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and {os.open, os.mkdir, os.unlink, os.rmdir, os.rename, os.stat} <= os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.listdir in os.supports_fd
)


@contextmanager
def _refuse_links() -> Generator[None]:
    try:
        yield
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise StorageBackendError("Storage path contains a symlink or non-directory.") from exc
        raise


class Directory:
    def __init__(self, path: Path, fd: int | None) -> None:
        self.path = path
        self.fd = fd

    @contextmanager
    def child(self, name: str, *, create: bool = False) -> Generator[Directory]:
        path = self.path / name
        if self.fd is None:
            if create:
                path.mkdir(exist_ok=True)
            if not path.is_dir():
                raise FileNotFoundError(path)
            yield Directory(path, None)
            return
        with _refuse_links():
            if create:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, dir_fd=self.fd)
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            yield Directory(path, fd)
        finally:
            os.close(fd)

    def open(self, name: str, mode: Literal["rb", "xb"] = "rb") -> IO[bytes]:
        if self.fd is None:
            return (self.path / name).open(mode)
        flags = os.O_RDONLY if mode == "rb" else os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with _refuse_links():
            fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o666, dir_fd=self.fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StorageBackendError("Storage object is not a regular file.")
            return os.fdopen(fd, mode)
        except BaseException:
            os.close(fd)
            raise

    def stat(self, name: str) -> os.stat_result:
        if self.fd is None:
            return (self.path / name).stat()
        result = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        if stat.S_ISLNK(result.st_mode):
            raise StorageBackendError("Storage object is a symlink.")
        return result

    def names(self) -> list[str]:
        if self.fd is None:
            return [path.name for path in self.path.iterdir()]
        return os.listdir(self.fd)  # noqa: PTH208 — list the anchored descriptor

    def unlink(self, name: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            if self.fd is None:
                (self.path / name).unlink()
            else:
                os.unlink(name, dir_fd=self.fd)

    def replace(self, source: str, target: str) -> None:
        if self.fd is None:
            (self.path / source).replace(self.path / target)
        else:
            os.replace(source, target, src_dir_fd=self.fd, dst_dir_fd=self.fd)

    def remove_child(self, name: str) -> None:
        if self.fd is None:
            shutil.rmtree(self.path / name, ignore_errors=True)
            return
        # Only remove a directory whose contents were opened without following links.
        with self.child(name) as child:
            for entry in child.names():
                child.unlink(entry)
        os.rmdir(name, dir_fd=self.fd)


@contextmanager
def directory(
    root: Path, parts: tuple[str, ...] = (), *, create: bool = False
) -> Generator[Directory]:
    with ExitStack() as stack:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        if CONFINED:
            with _refuse_links():
                fd = os.open(root.resolve(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
        else:
            fd = None
            if not root.is_dir():
                raise FileNotFoundError(root)
        current = Directory(root, fd)
        for part in parts:
            current = stack.enter_context(current.child(part, create=create))
        yield current


@asynccontextmanager
async def working_directory(
    root: Path, parts: tuple[str, ...] = (), *, create: bool = False
) -> AsyncGenerator[Directory]:
    stack = ExitStack()
    try:
        yield await _io(stack.enter_context, directory(root, parts, create=create))
    finally:
        await _io(stack.close)


@asynccontextmanager
async def opened_file(
    parent: Directory, name: str, mode: Literal["rb", "xb"] = "rb"
) -> AsyncGenerator[IO[bytes]]:
    stack = ExitStack()

    def open_file() -> IO[bytes]:
        return stack.enter_context(parent.open(name, mode))

    try:
        yield await _io(open_file)
    finally:
        await _io(stack.close)


@asynccontextmanager
async def atomic_file(parent: Directory, name: str) -> AsyncGenerator[IO[bytes]]:
    temporary = f"{name}.{uuid.uuid4().hex}.tmp"
    try:
        async with opened_file(parent, temporary, "xb") as file:
            yield file
        await _io(parent.replace, temporary, name)
    finally:
        with contextlib.suppress(OSError):
            await _io(parent.unlink, temporary)


class FileStream:
    """Own an eagerly opened file, including when closed before first iteration."""

    def __init__(self, length: int | None = None) -> None:
        self.file: IO[bytes] | None = None
        self.remaining = length

    def open(self, root: Path, parts: tuple[str, ...], name: str, start: int) -> None:
        with directory(root, parts) as parent:
            self.file = parent.open(name)
        self.file.seek(start)

    def __aiter__(self) -> FileStream:
        return self

    async def __anext__(self) -> bytes:
        if self.file is None or self.file.closed:
            raise StopAsyncIteration
        try:
            if self.remaining is not None and self.remaining <= 0:
                await self.aclose()
                raise StopAsyncIteration
            size = constants.DEFAULT_CHUNK_SIZE
            if self.remaining is not None:
                size = min(size, self.remaining)
            chunk = await _io(self.file.read, size)
            if not chunk:
                await self.aclose()
                raise StopAsyncIteration
            if self.remaining is not None:
                self.remaining -= len(chunk)
            return chunk
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        if self.file is not None and not self.file.closed:
            await _io(self.file.close)
