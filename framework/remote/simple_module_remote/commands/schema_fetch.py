"""Fetch and vet a live schema before ``schema sync`` stores it."""

from __future__ import annotations

from collections.abc import Iterator
from typing import NamedTuple

import httpx

from simple_module_remote.commands.generated import operation_command
from simple_module_remote.commands.schema_source import MALFORMED
from simple_module_remote.generate.operations import invalid_cli_names
from simple_module_remote.generate.tree import TreeError, build_groups
from simple_module_remote.generate.validate import schema_problems
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import ApiError
from simple_module_remote.output.sanitize import sanitize
from simple_module_remote.schema.cache import MAX_SCHEMA_BYTES, SchemaCacheError, parse_schema

__all__ = ["OPENAPI_PATH", "Fetched", "fetch_schema", "replayable_etag", "vet_schema"]

OPENAPI_PATH = "/api/_meta/openapi"
MAX_ETAG_CHARS = 256
CHUNK = 64 * 1024
IDENTITY = "identity"
HTTP_OK = 200


class Fetched(NamedTuple):
    status: int
    data: bytes
    etag: str | None


def _too_large() -> SchemaCacheError:
    return SchemaCacheError(f"the schema is larger than {MAX_SCHEMA_BYTES} bytes")


def replayable_etag(value: str | None) -> str | None:
    """*value* when it can be stored and sent back as ``If-None-Match`` (printable ASCII)."""
    if value is None or len(value) > MAX_ETAG_CHARS:
        return None
    return value if value.isascii() and value.isprintable() else None


def _safe_etag(value: str | None, client: ApiClient) -> str | None:
    tag = replayable_etag(value)
    return tag if tag is not None and client.redact(tag) == tag else None


def fetch_schema(client: ApiClient, headers: dict[str, str]) -> Fetched:
    """``GET`` the schema without following redirects, reading at most the byte budget.

    The body is requested uncompressed and a compressed answer is refused, so the budget
    bounds what is held in memory. Transport failures while reading raise ``ApiError(0)``.
    """
    wanted = {**headers, "Accept-Encoding": IDENTITY}
    try:
        with client.stream("GET", OPENAPI_PATH, headers=wanted, follow=False) as response:
            if response.status_code != HTTP_OK:
                return Fetched(response.status_code, b"", None)
            encoding = response.headers.get("Content-Encoding", IDENTITY).strip().lower()
            if encoding not in ("", IDENTITY):
                raise SchemaCacheError("the server compressed the schema; refusing to inflate it")
            declared = response.headers.get("Content-Length", "")
            if declared.isascii() and declared.isdigit() and int(declared) > MAX_SCHEMA_BYTES:
                raise _too_large()
            chunks, size = [], 0
            for chunk in response.iter_bytes(CHUNK):  # no Content-Encoding: nothing decoded
                size += len(chunk)
                if size > MAX_SCHEMA_BYTES:
                    raise _too_large()
                chunks.append(chunk)
            etag = _safe_etag(response.headers.get("ETag"), client)
    except (httpx.HTTPError, httpx.StreamError) as exc:
        raise ApiError(0, message=f"reading the schema failed: {type(exc).__name__}") from None
    return Fetched(HTTP_OK, b"".join(chunks), etag)


def _strings(root: object) -> Iterator[str]:
    """Every key and string value in a JSON document, without recursion."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for key, value in node.items():
                yield str(key)
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)


def _forms(text: str) -> tuple[str, ...]:
    return (text, sanitize(text), "".join(ch for ch in text if ch.isprintable()))


def _carries_token(data: bytes, root: dict, client: ApiClient) -> bool:
    texts = [data.decode("utf-8", errors="replace")]
    texts.extend(_strings(root))
    return any(client.redact(form) != form for text in texts for form in _forms(text))


def vet_schema(data: bytes, client: ApiClient) -> dict:
    """The parsed schema, or :class:`SchemaCacheError` when it must not be stored.

    Refused: not OpenAPI, the credential anywhere in it (raw, decoded keys or values, or
    after control characters are removed), an ``x-cli-name`` outside the command-name
    alphabet, colliding command names, or a document the tree builder cannot handle.
    """
    if len(data) > MAX_SCHEMA_BYTES:
        raise _too_large()
    root = parse_schema(data)
    if _carries_token(data, root, client):
        raise SchemaCacheError("the schema contains the credential; refusing to store it")
    bad = invalid_cli_names(root)
    if bad:
        raise SchemaCacheError(f"invalid x-cli-name values: {', '.join(bad[:5])}")
    problems = schema_problems(root)
    if problems:
        raise SchemaCacheError(sanitize(f"the schema is unusable: {'; '.join(problems)}"))
    try:
        build_groups(root, operation_command)
    except TreeError as exc:
        raise SchemaCacheError(sanitize(str(exc))) from None
    except MALFORMED as exc:
        raise SchemaCacheError(f"the schema is malformed ({type(exc).__name__})") from None
    return root
