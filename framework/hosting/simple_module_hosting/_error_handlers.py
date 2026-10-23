"""Framework-wide exception handlers that render Inertia error pages."""

from __future__ import annotations

import logging

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from simple_module_core.exceptions import NotFoundError
from simple_module_core.permission_denied import PermissionDenied
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from simple_module_hosting._error_negotiation import _wants_json
from simple_module_hosting._error_page import render_error_page
from simple_module_hosting._observability import CorrelationIdMiddleware

logger = logging.getLogger(__name__)

_INERTIA_ERROR_STATUSES = frozenset({401, 403, 404, 413, 419, 422, 429, 500, 503})


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    # Preserve exception headers (WWW-Authenticate, Retry-After, ...) the way
    # FastAPI's stock handler does — on the rendered page as well as the JSON
    # body, since both answer with the same status.
    headers = getattr(exc, "headers", None)
    if exc.status_code in _INERTIA_ERROR_STATUSES and not _wants_json(request):
        detail = str(exc.detail) if exc.detail else ""
        required = exc.permission if isinstance(exc, PermissionDenied) else None
        return await render_error_page(request, exc.status_code, detail, headers, required)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


async def not_found_error_handler(request: Request, exc: NotFoundError) -> Response:
    if _wants_json(request):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    return await render_error_page(request, 404, str(exc))


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Return an Inertia error page for browser requests with invalid params.

    Same negotiation rule as 403/404/500 (``_wants_json``), so one request
    never sees two different error shapes depending on the error class.
    """
    if _wants_json(request):
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
    return await render_error_page(request, 422, "The requested URL contains invalid parameters.")


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled exception: %s", exc)
    if _wants_json(request):
        response: Response = JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
        )
    else:
        response = await render_error_page(request, 500, "")
    # A catch-all `Exception` handler runs in Starlette's ServerErrorMiddleware,
    # which wraps *outside* CorrelationIdMiddleware, so the response never
    # passes through it. Without this the 500 — the one response a caller most
    # needs to quote back to support — is the one without the header.
    cid = getattr(request.state, "correlation_id", "")
    if cid:
        response.headers.setdefault(CorrelationIdMiddleware.HEADER, cid)
    return response
