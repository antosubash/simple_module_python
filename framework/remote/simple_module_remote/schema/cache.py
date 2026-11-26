"""The live schema cache: ``<cache>/<env>/openapi.json`` plus ``meta.json``.

Both files are owner-only (0600) in owner-only directories (0700) opened by
descriptor (``config/_private_dir.py``); reads are size-bounded. ``meta.json``
binds the schema to the base URL it was fetched from and to its SHA-256, so a URL
change or a torn write invalidates the cache. Neither file ever holds a credential.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from simple_module_remote.config._private_dir import PrivateDir, PrivateDirError
from simple_module_remote.config.paths import cache_dir

__all__ = [
    "LOCK_FILENAME",
    "MAX_SCHEMA_BYTES",
    "CacheMeta",
    "CachedSchema",
    "SchemaCacheError",
    "load_cached",
    "load_from",
    "open_cache",
    "parse_schema",
    "schema_digest",
    "touch_in",
    "write_to",
]

SCHEMA_FILENAME = "openapi.json"
META_FILENAME = "meta.json"
LOCK_FILENAME = "sync.lock"
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_META_BYTES = 64 * 1024
_META_TEXT_FIELDS = ("url", "origin", "fingerprint", "fetched_at")


class SchemaCacheError(Exception):
    """An unusable cache entry; the message says why and is safe to show."""


@dataclass(frozen=True)
class CacheMeta:
    url: str  # the environment's normalised base URL, path included
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
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise SchemaCacheError("the schema is not valid JSON") from None
    if not (
        isinstance(root, dict)
        and isinstance(root.get("openapi"), str)
        and isinstance(root.get("paths"), dict)
    ):
        raise SchemaCacheError("the schema is not an OpenAPI document")
    return root


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def open_cache(cli: str, env: str, *, create: bool) -> PrivateDir:
    """The env's cache directory, opened by descriptor (``fd`` is None when absent)."""
    try:
        return PrivateDir(cache_dir(cli), env, create=create)
    except PrivateDirError as exc:
        raise SchemaCacheError(str(exc)) from None


def _read(store: PrivateDir, name: str, limit: int) -> bytes | None:
    try:
        return store.read(name, limit)
    except PrivateDirError as exc:
        raise SchemaCacheError(str(exc)) from None


def read_meta(store: PrivateDir) -> CacheMeta | None:
    raw = _read(store, META_FILENAME, MAX_META_BYTES)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        data = None
    etag = data.get("etag") if isinstance(data, dict) else None
    if not (
        isinstance(data, dict)
        and all(isinstance(data.get(key), str) for key in _META_TEXT_FIELDS)
        and (etag is None or isinstance(etag, str))
    ):
        raise SchemaCacheError("the cached schema metadata is corrupt")
    return CacheMeta(data["url"], data["origin"], data["fingerprint"], etag, data["fetched_at"])


def load_from(store: PrivateDir, env: str, url: str, origin: str) -> CachedSchema | None:
    """The cached schema for ``env``; ``None`` when there is none.

    Raises :class:`SchemaCacheError` when the entry exists but cannot be used: fetched
    for another URL, altered or torn since, too large, or unsafe to read.
    """
    meta = read_meta(store)
    if meta is None:
        return None
    if meta.url != url or meta.origin != origin:
        raise SchemaCacheError(
            f"the cached schema for {env!r} came from {meta.url}, "
            f"but the environment now points at {url}"
        )
    raw = _read(store, SCHEMA_FILENAME, MAX_SCHEMA_BYTES)
    if raw is None or schema_digest(raw) != meta.fingerprint:
        raise SchemaCacheError(f"the cached schema for {env!r} is incomplete or was altered")
    return CachedSchema(store.path / SCHEMA_FILENAME, parse_schema(raw), meta)


def load_cached(cli: str, env: str, url: str, origin: str) -> CachedSchema | None:
    with open_cache(cli, env, create=False) as store:
        return load_from(store, env, url, origin)


def _write_meta(store: PrivateDir, meta: CacheMeta) -> None:
    body = json.dumps(
        {
            "url": meta.url,
            "origin": meta.origin,
            "fingerprint": meta.fingerprint,
            "etag": meta.etag,
            "fetched_at": meta.fetched_at,
        },
        indent=2,
    )
    try:
        store.write(META_FILENAME, body.encode("utf-8"))
    except PrivateDirError as exc:
        raise SchemaCacheError(str(exc)) from None


def write_to(store: PrivateDir, url: str, origin: str, data: bytes, etag: str | None) -> CacheMeta:
    """Store a fetched schema (validated first) and its metadata; returns the metadata."""
    parse_schema(data)
    meta = CacheMeta(url, origin, schema_digest(data), etag, _now())
    try:
        # Schema first: until meta.json names its digest, a reader rejects the pair.
        store.write(SCHEMA_FILENAME, data)
    except PrivateDirError as exc:
        raise SchemaCacheError(str(exc)) from None
    _write_meta(store, meta)
    return meta


def touch_in(store: PrivateDir, meta: CacheMeta) -> CacheMeta:
    """Record a revalidation (HTTP 304): same schema, new ``fetched_at``."""
    fresh = replace(meta, fetched_at=_now())
    _write_meta(store, fresh)
    return fresh
