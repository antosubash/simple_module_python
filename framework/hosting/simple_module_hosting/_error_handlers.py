"""Framework-wide exception handlers that render Inertia error pages."""

from __future__ import annotations

import logging

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_core.exceptions import NotFoundError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from simple_module_hosting._inertia_shared import _INERTIA_HEADER

logger = logging.getLogger(__name__)

_INERTIA_ERROR_STATUSES = frozenset({403, 404, 500})


def _explicit_accept_q(accept: str, media_type: str) -> float:
    """Quality the Accept header gives ``media_type`` by explicit listing.

    Only exact entries count (no ``*/*`` / ``type/*`` wildcards) — the
    negotiation below cares whether the caller *named* html or json, and at
    what preference. Malformed q-values fall back to 1.0 per RFC 9110.
    """
    for part in accept.split(","):
        media, _, params = part.partition(";")
        if media.strip().lower() != media_type:
            continue
        q = 1.0
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    q = float(value.strip())
                except ValueError:
                    q = 1.0
        return q
    return 0.0


def _wants_json(request: Request) -> bool:
    """API callers get JSON error bodies; browser-shaped requests get the page.

    A request that explicitly accepts ``text/html`` is a browser navigation —
    and those reach ``/api/*`` too (OAuth login links, file-download hrefs) —
    so it always gets the rendered page, unless the caller *prefers* JSON via
    q-values (``application/json, text/html;q=0.5`` is an API client keeping
    an html fallback, and ``text/html;q=0`` rules html out entirely). So does
    an Inertia visit (``X-Inertia`` header), whatever its Accept — an Inertia
    client can only consume Inertia-protocol responses, never a bare JSON
    body. Otherwise ``/api/*``, the documented prefix for every module's
    JSON surface (``ModuleMeta.route_prefix``), gets JSON — a bare
    ``fetch()`` sends ``Accept: */*`` — as does an explicit
    ``Accept: application/json`` anywhere else.
    """
    if request.headers.get(_INERTIA_HEADER):
        return False
    accept = request.headers.get("accept", "")
    html_q = _explicit_accept_q(accept, "text/html")
    json_q = _explicit_accept_q(accept, "application/json")
    if html_q > 0 and html_q >= json_q:
        return False
    path = request.url.path
    if path == "/api" or path.startswith("/api/"):
        return True
    return json_q > 0


async def render_error_page(request: Request, status_code: int, message: str) -> Response:
    config: InertiaConfig = request.app.state.sm.inertia_config
    try:
        inertia = Inertia(request, config)
        # This builds its own Inertia instead of going through get_inertia, so
        # the share step has to be repeated here. Without it the error page
        # renders raw translation keys (host.error.not_found_title) and loses
        # auth/menus, so a signed-in user's 404 has no layout.
        shared = getattr(request.state, "inertia_shared", None)
        if shared:
            inertia.share(**shared)
        # The correlation id is the only handle a user has on their own failed
        # request — without it a support report is just "it broke". It is already
        # on every log line for this request, so quoting it back makes the page
        # and the logs joinable.
        response = await inertia.render(
            "Error",
            {
                "status": status_code,
                "message": message,
                "correlation_id": getattr(request.state, "correlation_id", "") or "",
            },
        )
        response.status_code = status_code
        return response
    except InertiaVersionConflictException as exc:
        return await inertia_version_conflict_exception_handler(request, exc)
    except Exception:
        # Fallback if Inertia rendering itself fails (e.g. missing session)
        logger.exception("Error page rendering failed, falling back to JSON")
        return JSONResponse(
            status_code=status_code, content={"detail": message or "Internal Server Error"}
        )


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if exc.status_code in _INERTIA_ERROR_STATUSES and not _wants_json(request):
        detail = str(exc.detail) if exc.detail else ""
        return await render_error_page(request, exc.status_code, detail)
    # Preserve exception headers (WWW-Authenticate, Retry-After, ...) the way
    # FastAPI's stock handler does.
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
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
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return await render_error_page(request, 500, "")
