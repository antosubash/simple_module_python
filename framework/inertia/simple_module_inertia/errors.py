"""Exception types and handlers. Names match upstream — hosting imports them."""

from __future__ import annotations

from fastapi import Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.responses import RedirectResponse

from simple_module_inertia.response import back_url, version_conflict
from simple_module_inertia.validation import errors_from_validation, scope_errors


class InertiaVersionConflictException(Exception):  # noqa: N818 - upstream name; hosting imports it
    """Raised on a GET whose ``X-Inertia-Version`` no longer matches ours."""

    def __init__(self, url: str, *, version: str = "") -> None:
        self.url = url
        self.version = version
        super().__init__()


async def inertia_version_conflict_exception_handler(
    _: Request, exc: InertiaVersionConflictException
) -> Response:
    return version_conflict(str(exc.url), exc.version)


async def inertia_request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Flash validation errors and send the browser back, scoped by error bag."""
    if "x-inertia" not in request.headers:
        return await request_validation_exception_handler(request, exc)

    errors = errors_from_validation(exc.errors(), request_source=True)
    request.session["_errors"] = scope_errors(errors, request.headers.get("X-Inertia-Error-Bag"))

    code = (
        status.HTTP_307_TEMPORARY_REDIRECT if request.method == "GET" else status.HTTP_303_SEE_OTHER
    )
    return RedirectResponse(url=back_url(request), status_code=code)
