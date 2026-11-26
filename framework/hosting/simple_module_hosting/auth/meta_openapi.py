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
import re

from fastapi import APIRouter, Depends, Request, Response

from simple_module_hosting.auth.host_permissions import HostPermissions
from simple_module_hosting.auth.permissions import RequiresPermission

__all__ = ["META_OPENAPI_PATH", "router"]

META_OPENAPI_PATH = "/api/_meta/openapi"
_CACHE_CONTROL = "private, no-cache"
_JSON = "application/json"
# One entity-tag, then a comma (with optional whitespace) or the end of the value.
_ENTITY_TAG = re.compile(r'(?:W/)?"([^"]*)"\s*(?:,\s*|$)')

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


def _entity_tags(field: str) -> list[str] | None:
    """The opaque tags of one ``If-None-Match`` field value, ``W/`` dropped.

    Quote-aware (RFC 9110 §8.8.3): a comma inside quotes is part of a tag, not a
    separator. ``None`` when the value is malformed, so it matches nothing.
    """
    tags: list[str] = []
    pos = 0
    while True:
        found = _ENTITY_TAG.match(field, pos)
        if found is None:
            return None
        tags.append(found.group(1))
        pos = found.end()
        if pos == len(field):
            return tags


def _matches(fields: list[str], etag: str) -> bool:
    """Weak comparison over every field value; ``*`` only as an entire field value."""
    bare = etag.removeprefix("W/").strip('"')
    for field in fields:
        if field.strip() == "*":
            return True
        if bare in (_entity_tags(field.strip()) or ()):
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
    if _matches(request.headers.getlist("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=_JSON, headers=headers)
