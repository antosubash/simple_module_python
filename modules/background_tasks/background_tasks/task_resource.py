"""Explicit resource references on task messages (#709)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from background_tasks.constants import (
    RESOURCE_REF_MAX_LENGTH,
    SM_RESOURCE_ID_HEADER,
    SM_RESOURCE_TYPE_HEADER,
)
from background_tasks.tenant_context import header_of_request

if TYPE_CHECKING:
    from celery.canvas import Signature

_TYPE_NAME = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")


def resource_headers(resource_type: str, resource_id: str) -> dict[str, str]:
    """Validate before publishing; never silently truncate an identity."""
    if (
        not isinstance(resource_type, str)
        or len(resource_type) > RESOURCE_REF_MAX_LENGTH
        or not _TYPE_NAME.fullmatch(resource_type)
        or not isinstance(resource_id, str)
        or not resource_id.strip()
        or len(resource_id) > RESOURCE_REF_MAX_LENGTH
        or any(ord(c) < 32 or ord(c) == 127 for c in resource_id)
    ):
        raise ValueError("Invalid task resource reference")
    return {SM_RESOURCE_TYPE_HEADER: resource_type, SM_RESOURCE_ID_HEADER: resource_id}


def with_task_resource(signature: Signature, *, resource_type: str, resource_id: str) -> Signature:
    """Clone a signature, preserving its other options and headers."""
    headers = resource_headers(resource_type, resource_id)
    return signature.clone().set(headers={**(signature.options.get("headers") or {}), **headers})


def message_resource(*, headers: dict | None = None, request: Any = None) -> dict[str, str]:
    """Accept a validated pair only; malformed external messages grant no access."""
    kind = (headers or {}).get(SM_RESOURCE_TYPE_HEADER)
    key = (headers or {}).get(SM_RESOURCE_ID_HEADER)
    if headers is None:
        kind = header_of_request(request, SM_RESOURCE_TYPE_HEADER)
        key = header_of_request(request, SM_RESOURCE_ID_HEADER)
    if not isinstance(kind, str) or not isinstance(key, str):
        return {}
    try:
        resource_headers(kind, key)
    except ValueError:
        return {}
    return {"resource_type": kind, "resource_id": key}
