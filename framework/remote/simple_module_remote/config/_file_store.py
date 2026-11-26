"""Fallback credential file: ``credentials.toml``, mode 0600 in a 0700 directory."""

import os
import secrets
import tomllib
from pathlib import Path

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

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        if self._path.stat().st_mode & LOOSE_MODE_MASK:
            raise FileStoreError(
                f"refusing to read {self._path}: it is accessible to other users "
                f"(run `chmod 600 {self._path}`)"
            )
        try:
            raw = tomllib.loads(self._path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
            raise FileStoreError(f"cannot read {self._path}: file is corrupt") from None
        out: dict[str, dict[str, str]] = {}
        for key, table in raw.items():
            if isinstance(table, dict) and all(
                isinstance(table.get(f), str) for f in (TOKEN_FIELD, ORIGIN_FIELD)
            ):
                out[key] = {f: table[f] for f in (TOKEN_FIELD, ORIGIN_FIELD)}
        return out

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(tomli_w.dumps(data).encode("utf-8"))
            tmp.replace(self._path)
        finally:
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
