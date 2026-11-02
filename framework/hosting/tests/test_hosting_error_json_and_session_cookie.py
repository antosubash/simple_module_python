"""GH #346 (unhandled 500 / NotFoundError negotiate JSON) and #349 (anonymous
API responses must not set a session cookie)."""

from __future__ import annotations

import httpx
import pytest
from simple_module_core.exceptions import NotFoundError


@pytest.fixture
async def boom_client(app, authenticated_client):
    @app.get("/api/_t/boom")
    async def api_boom() -> None:
        raise RuntimeError("kaboom")

    @app.get("/_t/boom")
    async def view_boom() -> None:
        raise RuntimeError("kaboom")

    @app.get("/api/_t/missing")
    async def api_missing() -> None:
        raise NotFoundError("Widget", 7)

    @app.get("/_t/missing")
    async def view_missing() -> None:
        raise NotFoundError("Widget", 7)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        c.cookies.update(authenticated_client.cookies)
        yield c


class TestUnhandledErrorNegotiation:
    async def test_api_500_is_json(self, boom_client: httpx.AsyncClient) -> None:
        resp = await boom_client.get("/api/_t/boom", headers={"Accept": "application/json"})
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"detail": "Internal Server Error"}
        assert resp.headers.get("x-correlation-id")

    async def test_api_500_with_wildcard_accept_is_json(
        self, boom_client: httpx.AsyncClient
    ) -> None:
        resp = await boom_client.get("/api/_t/boom")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal Server Error"}

    async def test_page_500_is_still_html(self, boom_client: httpx.AsyncClient) -> None:
        resp = await boom_client.get("/_t/boom", headers={"Accept": "text/html"})
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("text/html")
        assert "data-page" in resp.text
        assert resp.headers.get("x-correlation-id")

    async def test_api_not_found_error_is_json(self, boom_client: httpx.AsyncClient) -> None:
        resp = await boom_client.get("/api/_t/missing")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Widget with id '7' not found"}

    async def test_page_not_found_error_is_html(self, boom_client: httpx.AsyncClient) -> None:
        resp = await boom_client.get("/_t/missing", headers={"Accept": "text/html"})
        assert resp.status_code == 404
        assert "data-page" in resp.text


class TestAnonymousSessionCookie:
    async def test_anonymous_api_get_sets_no_cookie(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/definitely/not/a/route")
        assert "set-cookie" not in resp.headers
        assert "cookie" not in resp.headers.get("vary", "").lower()

    async def test_anonymous_health_sets_no_cookie(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        assert "set-cookie" not in resp.headers

    async def test_anonymous_page_load_still_remembers_locale(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.get("/users/login", headers={"Accept": "text/html"})
        assert "session=" in resp.headers.get("set-cookie", "")
