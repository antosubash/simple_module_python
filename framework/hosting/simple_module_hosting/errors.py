"""Public error rendering for module exception handlers (#684)."""

from collections.abc import Mapping

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from simple_module_hosting._error_negotiation import _wants_json
from simple_module_hosting._error_page import render_error_page as _render_error_page


async def render_error_page(
    request: Request,
    status_code: int,
    detail: str,
    headers: Mapping[str, str] | None = None,
    *,
    required_permission: str | None = None,
) -> Response:
    """Return standard JSON for API clients or the Inertia Error page for browsers.

    Uses the framework's content negotiation, shared layout props and rendering
    fallback. Status and supplied headers survive either response format.
    ``required_permission`` optionally identifies the permission a 403 lacked.
    """
    if _wants_json(request):
        return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)
    return await _render_error_page(request, status_code, detail, headers, required_permission)
