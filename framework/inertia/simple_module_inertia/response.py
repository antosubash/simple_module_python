"""HTTP responses for each protocol outcome.

``Vary: Accept`` is upstream's value and is kept on purpose: hosting's
``InertiaCacheMiddleware`` appends ``X-Inertia`` on the way out and its tests
pin today's header set.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request, status
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


def back_url(request: Request) -> str:
    """The ``Referer`` reduced to a root-relative path on this site, else ``/``.

    Redirecting to the raw header is an open redirect: any page can link here
    with a ``Referer`` on another origin. Only the path and query are kept, so
    the scheme (which differs behind a TLS-terminating proxy) never matters.
    """
    raw = request.headers.get("Referer")
    if not raw or "\r" in raw or "\n" in raw:
        return "/"
    parts = urlsplit(raw)
    if parts.scheme not in ("", "http", "https"):
        return "/"
    if (parts.scheme or parts.netloc) and parts.netloc != request.url.netloc:
        return "/"
    path = parts.path
    if not path.startswith("/") or path.startswith(("//", "/\\")):
        return "/"
    return urlunsplit(("", "", path, parts.query, ""))
