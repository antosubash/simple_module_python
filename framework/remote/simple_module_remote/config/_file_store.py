"""Fallback credential file: ``credentials.toml``, mode 0600 in a 0700 directory."""

import contextlib
import errno
import os
import secrets
import stat
import tomllib
from collections.abc import Generator

import tomli_w

from simple_module_remote.config.paths import config_dir

CREDENTIALS_FILENAME = "credentials.toml"
LOCK_SUFFIX = ".lock"
KEYRING_LOCK = "keyring.lock"
TOKEN_FIELD = "token"
ORIGIN_FIELD = "origin"
PIN_FIELDS = ("tenant_id", "tenant_slug")  # optional: the tenant the token was pinned to
LOOSE_MODE_MASK = 0o077


_LOCK_FAILED = "cannot lock the credential store"


def _lock_exclusive(fd: int) -> bool:
    """Block until ``fd`` holds an exclusive advisory lock; ``False`` when nothing can lock.

    ``fcntl`` is POSIX-only; where it is missing (Windows) updates are not serialized
    across processes, which is the documented fallback.
    """
    try:
        import fcntl
    except ImportError:
        return False
    fcntl.flock(fd, fcntl.LOCK_EX)
    return True


def open_service_lock(service: str) -> int | None:
    """Open and exclusively lock the per-service keyring lock file.

    ``None`` where locking is unavailable (no ``fcntl``). Where it is available, failing to
    take the lock raises :class:`FileStoreError`: the caller must not write unserialised.
    """
    try:
        import fcntl  # noqa: F401  (only to know whether locking exists here)
    except ImportError:
        return None
    directory = config_dir(service)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(directory / KEYRING_LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise FileStoreError(
            f"cannot lock the credential store: {exc.__class__.__name__}"
        ) from None
    try:
        _lock_exclusive(fd)
    except OSError as exc:
        os.close(fd)
        raise FileStoreError(
            f"cannot lock the credential store: {exc.__class__.__name__}"
        ) from None
    return fd


class FileStoreError(Exception):
    """Unusable credentials file; the message never contains a token."""


class FileStore:
    def __init__(self, cli: str) -> None:
        if not (hasattr(os, "O_NOFOLLOW") and hasattr(os, "getuid")):
            raise FileStoreError(
                "no secure file credential store on this platform; install an OS keyring backend"
            )
        self._path = config_dir(cli) / CREDENTIALS_FILENAME

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            fd = os.open(self._path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return {}
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise FileStoreError(f"refusing to read {self._path}: it is a symlink") from None
            raise FileStoreError(f"cannot read {self._path}") from None
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise FileStoreError(f"refusing to read {self._path}: not a regular file")
            if info.st_uid != os.getuid():
                raise FileStoreError(f"refusing to read {self._path}: owned by another user")
            if info.st_mode & LOOSE_MODE_MASK:
                raise FileStoreError(
                    f"refusing to read {self._path}: it is accessible to other users "
                    f"(run `chmod 600 {self._path}`)"
                )
            try:
                raw = tomllib.loads(handle.read().decode("utf-8"))
            except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
                raise FileStoreError(
                    f"cannot read {self._path}: file is corrupt; delete it and log in again"
                ) from None
        out: dict[str, dict[str, str]] = {}
        for key, table in raw.items():
            if isinstance(table, dict) and all(
                isinstance(table.get(f), str) for f in (TOKEN_FIELD, ORIGIN_FIELD)
            ):
                out[key] = {
                    f: table[f]
                    for f in (TOKEN_FIELD, ORIGIN_FIELD, *PIN_FIELDS)
                    if isinstance(table.get(f), str)
                }
        return out

    def _secure_dir(self) -> None:
        directory = self._path.parent
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = directory.stat()
            if info.st_uid == os.getuid() and info.st_mode & LOOSE_MODE_MASK:
                directory.chmod(0o700)
                info = directory.stat()
        except OSError as exc:
            raise FileStoreError(f"cannot prepare {directory}: {exc.__class__.__name__}") from None
        if info.st_mode & LOOSE_MODE_MASK:
            raise FileStoreError(f"refusing to write in {directory}: it is not private")

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        self._secure_dir()
        tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(tomli_w.dumps(data).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(self._path)
        except OSError as exc:
            raise FileStoreError(f"cannot write {self._path}: {exc.__class__.__name__}") from None
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def get(self, key: str) -> dict[str, str] | None:
        return self._load().get(key)

    @contextlib.contextmanager
    def _locked(self) -> Generator[None]:
        """Serialize read-modify-write cycles across processes on a sibling lock file."""
        self._secure_dir()
        lock_path = self._path.with_name(self._path.name + LOCK_SUFFIX)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            _lock_exclusive(fd)
        except OSError as exc:
            raise FileStoreError(f"cannot lock {lock_path}: {exc.__class__.__name__}") from None
        try:
            yield
        finally:
            os.close(fd)  # closing the descriptor releases the lock

    def put(self, key: str, token: str, origin: str, pins: dict[str, str] | None = None) -> None:
        with self._locked():
            data = self._load()
            data[key] = {TOKEN_FIELD: token, ORIGIN_FIELD: origin, **(pins or {})}
            self._write(data)

    def delete(self, key: str) -> bool:
        with self._locked():
            data = self._load()
            if key not in data:
                return False
            del data[key]
            self._write(data)
            return True

    def keys(self) -> list[str]:
        return list(self._load())
