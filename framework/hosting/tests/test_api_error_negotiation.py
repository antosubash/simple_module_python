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
from simple_module_hosting._error_handlers import _wants_json, http_exception_handler
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse


def _request(path: str, accept: str = "*/*", method: str = "GET", inertia: bool = False) -> Request:
    headers = [(b"accept", accept.encode())]
    if inertia:
        headers.append((b"x-inertia", b"true"))
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
            "headers": headers,
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

    def test_browser_navigation_to_api_path_keeps_html_page(self) -> None:
        """OAuth login links and file-download hrefs are real ``<a>``
        navigations under /api/*; a browser Accept (text/html) must keep the
        rendered error page rather than dumping raw JSON in the tab."""
        browser_accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        assert not _wants_json(_request("/api/users/auth/github/login", accept=browser_accept))
        assert _wants_json(_request("/api/users/auth/github/login"))  # bare fetch: */*

    def test_json_preferring_accept_with_html_fallback_gets_json(self) -> None:
        """`application/json, text/html;q=0.5` is an API client keeping an
        html fallback — q-values decide, mentioning text/html must not."""
        assert _wants_json(_request("/pagebuilder/", accept="application/json, text/html;q=0.5"))
        assert _wants_json(_request("/api/x", accept="application/json, text/html;q=0.1"))

    def test_html_q_zero_is_not_browser_shaped(self) -> None:
        """`text/html;q=0` explicitly rules html out (RFC 9110)."""
        assert _wants_json(_request("/api/x", accept="text/html;q=0"))

    def test_html_q_zero_on_view_path_with_json_mentioned_gets_json(self) -> None:
        """`text/html;q=0` must rule the page out globally, not just under
        /api/*: a view path with html explicitly excluded and json named
        (even at q=0, i.e. both technically "not acceptable") must never
        render the html page — json is the only thing on offer."""
        assert _wants_json(
            _request("/pagebuilder/", accept="text/html;q=0, application/json;q=0.5")
        )
        assert _wants_json(_request("/pagebuilder/", accept="text/html;q=0, application/json;q=0"))

    def test_html_q_zero_on_view_path_with_json_unmentioned_keeps_html_fallback(self) -> None:
        """When json isn't named at all, there's nothing else to offer — the
        pre-existing html fallback survives on a view path even though html
        was explicitly excluded."""
        assert not _wants_json(_request("/pagebuilder/", accept="text/html;q=0"))

    def test_browser_accept_still_wins_over_wildcard_json(self) -> None:
        """Real browser Accept lists text/html explicitly; */* covering json
        does not outrank it."""
        assert not _wants_json(
            _request("/api/x", accept="text/html,application/xml;q=0.9,*/*;q=0.8")
        )

    def test_inertia_visit_never_gets_bare_json(self) -> None:
        """An Inertia client can only consume Inertia-protocol responses —
        the X-Inertia header must keep the rendered page even when the visit
        also advertises Accept: application/json or targets /api/*."""
        assert not _wants_json(_request("/api/x", accept="application/json", inertia=True))
        assert not _wants_json(_request("/pagebuilder/", accept="application/json", inertia=True))

    async def test_json_error_keeps_exception_headers(self) -> None:
        """WWW-Authenticate / Retry-After set on the HTTPException must reach
        the JSON response, matching FastAPI's stock handler."""
        resp = await http_exception_handler(
            _request("/api/things"),
            HTTPException(status_code=401, detail="nope", headers={"WWW-Authenticate": "Bearer"}),
        )
        assert resp.headers["www-authenticate"] == "Bearer"


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
