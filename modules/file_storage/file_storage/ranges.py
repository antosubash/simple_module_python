"""HTTP ``Range`` support for streamed file bodies (RFC 9110 § 14).

Only a single byte range is honoured — ``bytes=a-b``, ``bytes=a-`` and the
suffix form ``bytes=-n`` — which is all COG/PMTiles readers send. Anything
else (multiple ranges, another unit, garbage) is ignored and the whole object
is sent with ``200``, as RFC 9110 permits. A well-formed range that starts at
or past the end of the object is ``416`` with ``Content-Range: bytes */size``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from fastapi import Request, Response, status
from fastapi.responses import StreamingResponse

from file_storage.backend_guard import require_backend
from file_storage.contracts.service import StorageBackend
from file_storage.models import StoredFile

# 19 digits bounds every value below 2**63; longer numbers are treated as
# malformed (full 200) rather than parsed into arbitrarily large ints.
_SPEC = re.compile(r"^\s*(\d{0,19})\s*-\s*(\d{0,19})\s*$")

UNSATISFIABLE: Final = "unsatisfiable"


@dataclass(frozen=True)
class ByteRange:
    """``start`` through ``end``, both inclusive, already clamped to the object."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_range(header: str | None, size: int) -> ByteRange | Literal["unsatisfiable"] | None:
    """Resolve a ``Range`` header against an object of ``size`` bytes.

    ``None`` means "ignore it and send everything" (absent, malformed, multi-range
    or a unit other than bytes); :data:`UNSATISFIABLE` means ``416``.
    """
    if not header:
        return None
    unit, sep, spec = header.partition("=")
    if not sep or unit.strip().lower() != "bytes" or "," in spec:
        return None
    match = _SPEC.match(spec)
    if match is None:
        return None
    first, last = match.groups()
    if not first:
        if not last:
            return None
        suffix = int(last)
        if suffix == 0 or size == 0:
            return UNSATISFIABLE
        return ByteRange(start=max(0, size - suffix), end=size - 1)
    start = int(first)
    if last and int(last) < start:
        return None  # syntactically invalid: RFC 9110 says ignore the header
    if start >= size:
        return UNSATISFIABLE
    end = min(int(last), size - 1) if last else size - 1
    return ByteRange(start=start, end=end)


def _range_header(request: Request, etag: str) -> str | None:
    """The ``Range`` to honour, dropped when an ``If-Range`` validator fails."""
    if_range = request.headers.get("if-range")
    if if_range is not None and if_range.strip() != etag:
        # A stale (or date-based) validator: the client's partial copy may be
        # of another version, so it gets the whole current object instead.
        return None
    return request.headers.get("range")


async def file_body_response(
    backend: StorageBackend,
    row: StoredFile,
    request: Request,
    *,
    headers: Mapping[str, str],
    etag: str,
) -> Response:
    """Stream ``row`` as ``200``, or the requested slice as ``206`` / ``416``.

    ``headers`` are the caller's headers for the full response, minus
    ``Content-Length``, which is set here. The backend is opened only for the
    response actually served, so a ranged request never opens the full object.
    Raises :class:`StorageNotFoundError` if the object is gone.
    """
    require_backend(backend, row)
    size = row.size_bytes
    get_range = getattr(backend, "get_range", None)
    parsed = parse_range(_range_header(request, etag), size) if get_range else None
    out = dict(headers)
    if get_range is not None:
        out["Accept-Ranges"] = "bytes"

    if parsed is None:
        body = await backend.get(row.key)
        out["Content-Length"] = str(size)
        return StreamingResponse(body, media_type=row.content_type, headers=out)

    if parsed == UNSATISFIABLE:
        out["Content-Range"] = f"bytes */{size}"
        # An explicit ``max-age`` would let a cache keep this error and replay it
        # to later requests for the whole object.
        out = {k: v for k, v in out.items() if k.lower() != "cache-control"}
        return Response(status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE, headers=out)

    assert isinstance(parsed, ByteRange) and get_range is not None
    ranged = await get_range(row.key, parsed.start, parsed.end)
    out["Content-Range"] = f"bytes {parsed.start}-{parsed.end}/{size}"
    out["Content-Length"] = str(parsed.length)
    return StreamingResponse(
        ranged,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=row.content_type,
        headers=out,
    )
