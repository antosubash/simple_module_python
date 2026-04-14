"""Framework-wide exception handlers that render Inertia error pages."""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

_INERTIA_ERROR_STATUSES = frozenset({403, 404, 500})


async def render_error_page(request: Request, status_code: int, message: str) -> Response:
    config: InertiaConfig = request.app.state.inertia_config
    try:
        inertia = Inertia(request, config)
        response = await inertia.render("Error", {"status": status_code, "message": message})
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
    if exc.status_code in _INERTIA_ERROR_STATUSES:
        detail = str(exc.detail) if exc.detail else ""
        return await render_error_page(request, exc.status_code, detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def not_found_error_handler(request: Request, exc: NotFoundError) -> Response:
    return await render_error_page(request, 404, str(exc))


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled exception: %s", exc)
    return await render_error_page(request, 500, "")
