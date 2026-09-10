"""Exception types and handlers. Names match upstream — hosting imports them."""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.responses import RedirectResponse


class InertiaVersionConflictException(Exception):
    """Raised on a GET whose ``X-Inertia-Version`` no longer matches ours."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__()


async def inertia_version_conflict_exception_handler(
    _: Request, exc: InertiaVersionConflictException
) -> Response:
    return Response(
        status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Location": str(exc.url)}
    )


def _field(loc: tuple[Any, ...]) -> Any:
    return loc[1] if len(loc) > 1 else loc[0]


async def inertia_request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Flash validation errors and send the browser back, scoped by error bag."""
    if "x-inertia" not in request.headers:
        return await request_validation_exception_handler(request, exc)

    errors: dict[str, Any] = {}
    bag = request.headers.get("X-Inertia-Error-Bag")
    for error in exc.errors():
        field = _field(tuple(error["loc"]))
        if bag is None:
            errors[field] = error["msg"]
        else:
            errors.setdefault(bag, {})[field] = error["msg"]
    request.session["_errors"] = errors

    code = (
        status.HTTP_307_TEMPORARY_REDIRECT
        if request.method == "GET"
        else status.HTTP_303_SEE_OTHER
    )
    return RedirectResponse(url=request.headers.get("Referer", "/"), status_code=code)
