"""The live schema cache: ``<cache>/<env>/openapi.json`` plus ``meta.json``.

Both files are owner-only (0600) in owner-only directories (0700), read without
following symlinks. ``meta.json`` binds the schema to the origin it was fetched
from and to its SHA-256, so a URL change or a torn write invalidates the cache.
Neither file ever holds a credential.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from simple_module_remote.config._file_store import (
    FileStoreError,
    read_private,
    secure_dir,
    write_private,
)
from simple_module_remote.config.paths import cache_dir

__all__ = [
    "CacheMeta",
    "CachedSchema",
    "SchemaCacheError",
    "load_cached",
    "parse_schema",
    "read_meta",
    "schema_digest",
    "touch_cache",
    "write_cache",
]

SCHEMA_FILENAME = "openapi.json"
META_FILENAME = "meta.json"
_META_TEXT_FIELDS = ("origin", "fingerprint", "fetched_at")


class SchemaCacheError(Exception):
    """An unusable cache entry; the message says why and is safe to show."""


@dataclass(frozen=True)
class CacheMeta:
    origin: str
    fingerprint: str  # full SHA-256 hex digest of openapi.json
    etag: str | None
    fetched_at: str  # ISO 8601, UTC

    def age_seconds(self, now: datetime | None = None) -> float | None:
        try:
            when = datetime.fromisoformat(self.fetched_at)
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, ((now or datetime.now(UTC)) - when).total_seconds())


@dataclass(frozen=True)
class CachedSchema:
    path: Path
    root: dict
    meta: CacheMeta


def schema_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_schema(data: bytes) -> dict:
    """An OpenAPI document: a JSON object with ``openapi`` text and a ``paths`` object."""
    try:
        root = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SchemaCacheError("the schema is not valid JSON") from None
    if not (
        isinstance(root, dict)
        and isinstance(root.get("openapi"), str)
        and isinstance(root.get("paths"), dict)
    ):
        raise SchemaCacheError("the schema is not an OpenAPI document")
    return root


def _env_dir(cli: str, env: str) -> Path:
    return cache_dir(cli) / env


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read(path: Path) -> bytes | None:
    try:
        return read_private(path)
    except FileStoreError as exc:
        raise SchemaCacheError(str(exc)) from None


def read_meta(cli: str, env: str) -> CacheMeta | None:
    raw = _read(_env_dir(cli, env) / META_FILENAME)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        data = None
    etag = data.get("etag") if isinstance(data, dict) else None
    if not (
        isinstance(data, dict)
        and all(isinstance(data.get(key), str) for key in _META_TEXT_FIELDS)
        and (etag is None or isinstance(etag, str))
    ):
        raise SchemaCacheError("the cached schema metadata is corrupt")
    return CacheMeta(data["origin"], data["fingerprint"], etag, data["fetched_at"])


def load_cached(cli: str, env: str, origin: str) -> CachedSchema | None:
    """The cached schema for ``env``; ``None`` when there is none.

    Raises :class:`SchemaCacheError` when the entry exists but cannot be used: fetched
    from another origin, altered or torn since, or unsafe to read.
    """
    meta = read_meta(cli, env)
    if meta is None:
        return None
    if meta.origin != origin:
        raise SchemaCacheError(
            f"the cached schema for {env!r} came from {meta.origin}, "
            f"but the environment now points at {origin}"
        )
    path = _env_dir(cli, env) / SCHEMA_FILENAME
    raw = _read(path)
    if raw is None or schema_digest(raw) != meta.fingerprint:
        raise SchemaCacheError(f"the cached schema for {env!r} is incomplete or was altered")
    return CachedSchema(path, parse_schema(raw), meta)


def _write_meta(cli: str, env: str, meta: CacheMeta) -> None:
    body = json.dumps(
        {
            "origin": meta.origin,
            "fingerprint": meta.fingerprint,
            "etag": meta.etag,
            "fetched_at": meta.fetched_at,
        },
        indent=2,
    )
    write_private(_env_dir(cli, env) / META_FILENAME, body.encode("utf-8"))


def write_cache(cli: str, env: str, origin: str, data: bytes, etag: str | None) -> CacheMeta:
    """Store a fetched schema (validated first) and its metadata; returns the metadata."""
    parse_schema(data)
    meta = CacheMeta(origin, schema_digest(data), etag, _now())
    try:
        secure_dir(cache_dir(cli))
        # Schema first: until meta.json names its digest, a reader rejects the pair.
        write_private(_env_dir(cli, env) / SCHEMA_FILENAME, data)
        _write_meta(cli, env, meta)
    except FileStoreError as exc:
        raise SchemaCacheError(str(exc)) from None
    return meta


def touch_cache(cli: str, env: str, meta: CacheMeta) -> CacheMeta:
    """Record a revalidation (HTTP 304): same schema, new ``fetched_at``."""
    fresh = CacheMeta(meta.origin, meta.fingerprint, meta.etag, _now())
    try:
        _write_meta(cli, env, fresh)
    except FileStoreError as exc:
        raise SchemaCacheError(str(exc)) from None
    return fresh
