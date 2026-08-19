"""API callers must get JSON error bodies, not the Inertia HTML error page.

``http_exception_handler`` used to render 403/404/500 as an Inertia page
unconditionally. A ``fetch`` against ``/api/*`` then received a full HTML
document — with the actual error detail (permission name, CSRF hint)
invisible to the caller. Requests under ``/api/`` or that explicitly prefer
``application/json`` must get the JSON ``{"detail": ...}`` body instead;
browser-shaped requests keep the rendered page.
"""

from __future__ import annotations

import httpx
from simple_module_hosting._error_handlers import http_exception_handler
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse


def _request(path: str, accept: str = "*/*", method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
            "headers": [(b"accept", accept.encode())],
        }
    )


class TestHandlerNegotiation:
    async def test_api_path_403_returns_json_detail(self) -> None:
        resp = await http_exception_handler(
            _request("/api/pagebuilder/pages", method="POST"),
            HTTPException(status_code=403, detail="Permission required: pagebuilder.edit"),
        )
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 403
        assert b"pagebuilder.edit" in resp.body

    async def test_api_path_404_returns_json(self) -> None:
        resp = await http_exception_handler(
            _request("/api/nope"), HTTPException(status_code=404, detail="Not Found")
        )
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 404

    async def test_json_accept_on_view_path_returns_json(self) -> None:
        resp = await http_exception_handler(
            _request("/pagebuilder/", accept="application/json"),
            HTTPException(status_code=403, detail="nope"),
        )
        assert isinstance(resp, JSONResponse)


class TestClientNegotiation:
    async def test_api_404_is_json(self, authenticated_client: httpx.AsyncClient) -> None:
        resp = await authenticated_client.get("/api/definitely/not/a/route")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert "detail" in resp.json()

    async def test_view_404_with_json_accept_is_json(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(
            "/definitely/not/a/route", headers={"Accept": "application/json"}
        )
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")

    async def test_view_404_default_accept_still_renders_page(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get("/definitely/not/a/route")
        assert resp.status_code == 404
        assert "data-page" in resp.text  # Inertia error page, unchanged behavior
