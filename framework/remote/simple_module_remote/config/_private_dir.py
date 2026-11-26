"""Owner-only directories handled by descriptor (the live schema cache).

Each directory is opened with ``O_DIRECTORY | O_NOFOLLOW`` and checked with ``fstat``
(owned by this user, mode 0700, tightened when we own a looser one). Every read, temp
file, rename and lock then goes through that descriptor (``dir_fd``), so swapping a
path component for a symlink after the check cannot redirect them. Where the platform
lacks ``dir_fd`` support (Windows), :class:`PrivateDirError` is raised and callers treat
the store as unavailable.
"""

from __future__ import annotations

import contextlib
import errno
import os
import secrets
import stat
from collections.abc import Generator
from pathlib import Path
from types import TracebackType

from simple_module_remote.config._file_store import LOOSE_MODE_MASK, _lock_exclusive

__all__ = ["PrivateDir", "PrivateDirError", "private_dirs_supported"]

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
# O_NONBLOCK: opening a FIFO must not wait for a writer; regular files ignore it.
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_NEW_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
_LOCK_FLAGS = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)


class PrivateDirError(Exception):
    """An unusable private directory or file; the message is safe to show."""


def private_dirs_supported() -> bool:
    needed = (os.open, os.mkdir, os.rename, os.unlink, os.stat)
    return (
        hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "getuid")
        and all(fn in os.supports_dir_fd for fn in needed)
    )


def _check_dir(fd: int, shown: Path) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise PrivateDirError(f"refusing to use {shown}: not a directory")
    if info.st_uid != os.getuid():
        raise PrivateDirError(f"refusing to use {shown}: owned by another user")
    if info.st_mode & LOOSE_MODE_MASK:
        os.fchmod(fd, 0o700)
        if os.fstat(fd).st_mode & LOOSE_MODE_MASK:
            raise PrivateDirError(f"refusing to use {shown}: it is not private")


def _open_dir(name: str | Path, shown: Path, parent: int | None, create: bool) -> int | None:
    """Open (creating if asked) one directory level; ``None`` when absent and not created."""
    if create:
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise PrivateDirError(f"refusing to use {shown}: not a plain directory") from None
        raise PrivateDirError(f"cannot open {shown}: {exc.__class__.__name__}") from None
    try:
        _check_dir(fd, shown)
    except BaseException:
        os.close(fd)
        raise
    return fd


class PrivateDir:
    """``<base>/<name>`` opened by descriptor; use as a context manager."""

    def __init__(self, base: Path, name: str, *, create: bool) -> None:
        if not private_dirs_supported():
            raise PrivateDirError("no secure file store on this platform")
        self.path = base / name
        self._fds: list[int] = []
        try:
            if create:
                base.parent.mkdir(parents=True, exist_ok=True)
            outer = _open_dir(base, base, None, create)
            if outer is None:
                self.fd = None
                return
            self._fds.append(outer)
            inner = _open_dir(name, self.path, outer, create)
            if inner is not None:
                self._fds.append(inner)
            self.fd = inner
        except OSError as exc:
            self.close()
            raise PrivateDirError(f"cannot prepare {self.path}: {exc.__class__.__name__}") from None
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> PrivateDir:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        while self._fds:
            os.close(self._fds.pop())

    def read(self, name: str, max_bytes: int) -> bytes | None:
        """An owner-only regular file's bytes (at most ``max_bytes``); ``None`` when absent."""
        if self.fd is None:
            return None
        shown = self.path / name
        try:
            fd = os.open(name, _READ_FLAGS, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise PrivateDirError(f"refusing to read {shown}: it is a symlink") from None
            raise PrivateDirError(f"cannot read {shown}") from None
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise PrivateDirError(f"refusing to read {shown}: not a regular file")
            if info.st_uid != os.getuid():
                raise PrivateDirError(f"refusing to read {shown}: owned by another user")
            if info.st_mode & LOOSE_MODE_MASK:
                raise PrivateDirError(f"refusing to read {shown}: it is accessible to other users")
            if info.st_size > max_bytes:
                raise PrivateDirError(f"refusing to read {shown}: larger than {max_bytes} bytes")
            try:
                data = handle.read(max_bytes + 1)
            except OSError:
                raise PrivateDirError(f"cannot read {shown}") from None
        if len(data) > max_bytes:
            raise PrivateDirError(f"refusing to read {shown}: larger than {max_bytes} bytes")
        return data

    def write(self, name: str, data: bytes) -> None:
        """Atomically replace ``name`` with ``data`` (mode 0600) inside this directory."""
        if self.fd is None:
            raise PrivateDirError(f"{self.path} is not open for writing")
        tmp = f".{name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        try:
            fd = os.open(tmp, _NEW_FLAGS, 0o600, dir_fd=self.fd)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        except OSError as exc:
            raise PrivateDirError(
                f"cannot write {self.path / name}: {exc.__class__.__name__}"
            ) from None
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=self.fd)

    @contextlib.contextmanager
    def locked(self, name: str) -> Generator[None]:
        """Hold an exclusive advisory lock on ``name`` in this directory."""
        if self.fd is None:
            raise PrivateDirError(f"{self.path} is not open for locking")
        try:
            fd = os.open(name, _LOCK_FLAGS, 0o600, dir_fd=self.fd)
        except OSError as exc:
            raise PrivateDirError(
                f"cannot lock {self.path / name}: {exc.__class__.__name__}"
            ) from None
        try:
            try:
                _lock_exclusive(fd)
            except OSError as exc:
                raise PrivateDirError(f"cannot lock {self.path / name}") from exc
            yield
        finally:
            os.close(fd)
