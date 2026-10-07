"""Shared 413 / 429 response building for the pipeline-level request guards.

The guards run as raw ASGI middleware, outside Starlette's exception handling,
so they cannot raise ``HTTPException``. They build the same two shapes the
exception handlers do: JSON for API callers, the Inertia error page otherwise
(negotiated by ``_wants_json``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

from simple_module_hosting._error_handlers import _wants_json, render_error_page


async def guard_response(
    scope: Scope,
    status_code: int,
    message: str,
    *,
    headers: Mapping[str, str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Response:
    request = Request(scope)
    if _wants_json(request):
        return JSONResponse(
            status_code=status_code,
            content={"detail": message, **(extra or {})},
            headers=dict(headers) if headers else None,
        )
    return await render_error_page(request, status_code, message, headers)


async def send_guard_response(
    scope: Scope,
    receive: Receive,
    send: Send,
    status_code: int,
    message: str,
    *,
    headers: Mapping[str, str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    response = await guard_response(scope, status_code, message, headers=headers, extra=extra)
    await response(scope, receive, send)
