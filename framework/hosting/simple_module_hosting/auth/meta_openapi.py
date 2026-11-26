"""Serve the live API schema to authenticated clients (#1178).

``GET /api/_meta/openapi`` returns ``app.openapi()`` — the same filtered,
security-annotated schema as ``/api/openapi.json`` — for a project CLI that
reads the running server's routes with its token. Unlike ``/api/openapi.json``
it is never anonymous (``openapi_public`` does not apply) and needs
``host.openapi.read``, which a token can carry as a scope. It is left out of
the schema it serves, so serving it does not change the bundled CLI schema.

The body is revalidated, not cached: ``private, no-cache`` with a weak ETag
over the serialized bytes, and a matching ``If-None-Match`` answers ``304``.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Request, Response

from simple_module_hosting.auth.host_permissions import HostPermissions
from simple_module_hosting.auth.permissions import RequiresPermission

__all__ = ["META_OPENAPI_PATH", "router"]

META_OPENAPI_PATH = "/api/_meta/openapi"
_CACHE_CONTROL = "private, no-cache"
_JSON = "application/json"

# No prefix: ``whoami.router`` (``/api/_meta``) includes this one, so boot mounts one router.
router = APIRouter()


def _serialized(request: Request) -> tuple[bytes, str]:
    """The schema's bytes and weak ETag, recomputed only when the schema object changes."""
    schema = request.app.openapi()
    cached = getattr(request.app.state, "_meta_openapi_body", None)
    if cached is not None and cached[0] is schema:
        return cached[1], cached[2]
    body = json.dumps(schema, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    etag = f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'
    request.app.state._meta_openapi_body = (schema, body, etag)
    return body, etag


def _matches(if_none_match: str, etag: str) -> bool:
    """Weak comparison (RFC 9110 §13.1.2): ``W/`` prefixes are ignored; ``*`` matches."""
    bare = etag.removeprefix("W/")
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate == "*" or candidate.removeprefix("W/") == bare:
            return True
    return False


@router.get(
    "/openapi",
    include_in_schema=False,
    dependencies=[Depends(RequiresPermission(HostPermissions.OPENAPI_READ))],
)
async def meta_openapi(request: Request) -> Response:
    """The live OpenAPI schema, revalidated by ETag."""
    body, etag = _serialized(request)
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=_JSON, headers=headers)
