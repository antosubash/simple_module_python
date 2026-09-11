"""HTTP responses for each protocol outcome.

``Vary: Accept`` is upstream's value and is kept on purpose: hosting's
``InertiaCacheMiddleware`` appends ``X-Inertia`` on the way out and its tests
pin today's header set.
"""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import RedirectResponse, Response

from simple_module_inertia.page import encode_page

InertiaResponse = HTMLResponse | JSONResponse

_JSON_HEADERS = {"X-Inertia": "true", "Vary": "Accept"}


def json_response(page: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=encode_page(page), headers=_JSON_HEADERS)


def version_conflict(url: str, version: str) -> Response:
    return Response(
        status_code=status.HTTP_409_CONFLICT,
        headers={"X-Inertia-Location": url, "X-Inertia-Version": version},
    )


def redirect(url: str, *, method: str) -> RedirectResponse:
    code = (
        status.HTTP_307_TEMPORARY_REDIRECT if method.upper() == "GET" else status.HTTP_303_SEE_OTHER
    )
    return RedirectResponse(url=url, status_code=code)


def location(url: str) -> Response:
    return Response(status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Location": url})


def fragment_redirect(url: str) -> Response:
    return Response(status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Redirect": url})
