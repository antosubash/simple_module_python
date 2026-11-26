"""Fallback credential file: ``credentials.toml``, mode 0600 in a 0700 directory."""

import contextlib
import errno
import os
import secrets
import stat
import tomllib

import tomli_w

from simple_module_remote.config.paths import config_dir

CREDENTIALS_FILENAME = "credentials.toml"
TOKEN_FIELD = "token"
ORIGIN_FIELD = "origin"
LOOSE_MODE_MASK = 0o077


class FileStoreError(Exception):
    """Unusable credentials file; the message never contains a token."""


class FileStore:
    def __init__(self, cli: str) -> None:
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
                out[key] = {f: table[f] for f in (TOKEN_FIELD, ORIGIN_FIELD)}
        return out

    def _secure_dir(self) -> None:
        try:
            self._ensure_private_dir()
        except OSError as exc:
            raise FileStoreError(
                f"cannot prepare {self._path.parent}: {exc.__class__.__name__}"
            ) from None

    def _ensure_private_dir(self) -> None:
        directory = self._path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.stat()
        if info.st_uid == os.getuid() and info.st_mode & LOOSE_MODE_MASK:
            directory.chmod(0o700)
            info = directory.stat()
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

    def get(self, key: str) -> tuple[str, str] | None:
        entry = self._load().get(key)
        return (entry[TOKEN_FIELD], entry[ORIGIN_FIELD]) if entry else None

    def put(self, key: str, token: str, origin: str) -> None:
        data = self._load()
        data[key] = {TOKEN_FIELD: token, ORIGIN_FIELD: origin}
        self._write(data)

    def delete(self, key: str) -> bool:
        data = self._load()
        if key not in data:
            return False
        del data[key]
        self._write(data)
        return True
