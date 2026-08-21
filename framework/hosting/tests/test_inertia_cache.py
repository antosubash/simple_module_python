"""An Inertia payload must never be cacheable as the page it belongs to.

The same URL answers twice — HTML for a full page load, JSON for a client-side
visit — and the only thing separating them is the ``X-Inertia`` request header.
Left unsaid, a cache stores one and serves it for the other, so opening a page
directly after visiting it through the SPA renders the raw payload. The payload
also carries this user's ``auth`` block, permissions and menus, so a shared
cache storing it is a disclosure bug as well as a broken page.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting._inertia_cache import (
    PAYLOAD_CACHE_CONTROL,
    InertiaCacheMiddleware,
    is_inertia_request,
)
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

_OK = 200
_INERTIA = {"X-Inertia": "true"}
#: What a public-content module might reasonably put on its own page.
_PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=600"
_SHARED_ETAG = 'W/"deadbeef"'


def _vary_fields(response: httpx.Response) -> set[str]:
    return {part.strip().lower() for part in response.headers.get("vary", "").split(",")}


def _build_app() -> Starlette:
    """A route that markets itself as publicly cacheable, both ways.

    Mirrors what the page-builder's public viewer does: one ETag and one
    ``Cache-Control`` computed from the page row, stamped on whichever
    representation the request asked for.
    """

    async def page(request):
        if is_inertia_request(request.scope):
            response: Response = JSONResponse(
                {"component": "PublicPage", "props": {"auth": {"user": "editor"}}},
                headers={"X-Inertia": "true", "Vary": "Accept"},
            )
        else:
            response = HTMLResponse("<!DOCTYPE html><title>Page</title>")
        response.headers["Cache-Control"] = _PUBLIC_CACHE
        response.headers["ETag"] = _SHARED_ETAG
        return response

    async def asset(request):
        return Response(b"body{}", media_type="text/css", headers={"ETag": _SHARED_ETAG})

    app = Starlette(routes=[Route("/p/home", page), Route("/static/app.css", asset)])
    app.add_middleware(InertiaCacheMiddleware)
    return app


@pytest.fixture
def cache_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_build_app()), base_url="http://test"
    )


class TestInertiaPayload:
    async def test_payload_is_not_stored_even_when_the_route_says_public(
        self, cache_client: httpx.AsyncClient
    ) -> None:
        """The route asked for `public`; the payload is per-user, so it loses."""
        async with cache_client as client:
            resp = await client.get("/p/home", headers=_INERTIA)

        assert resp.status_code == _OK
        assert resp.headers["cache-control"] == PAYLOAD_CACHE_CONTROL

    async def test_payload_carries_no_validator(self, cache_client: httpx.AsyncClient) -> None:
        """A shared ETag lets a cache revalidate its way back to the payload.

        The route stamps the same ETag on both representations, so a client
        holding the JSON could revalidate a *document* request into a 304 and
        keep rendering it. Nothing to revalidate means nothing to restore.
        """
        async with cache_client as client:
            resp = await client.get("/p/home", headers=_INERTIA)

        assert "etag" not in resp.headers

    async def test_payload_varies_on_the_header_that_selected_it(
        self, cache_client: httpx.AsyncClient
    ) -> None:
        async with cache_client as client:
            resp = await client.get("/p/home", headers=_INERTIA)

        assert "x-inertia" in _vary_fields(resp)
        # Whatever the route already listed stays listed.
        assert "accept" in _vary_fields(resp)


class TestMatchesUpstreamDetection:
    """``is_inertia_request`` must agree with ``fastapi-inertia``'s own check.

    Upstream's ``Inertia._is_inertia_request`` is ``"X-Inertia" in
    self._request.headers`` — presence only, any value. A stricter check here
    (e.g. requiring the value to equal ``"true"``) would disagree with it: a
    request the renderer treats as Inertia and answers with JSON would sail
    through this middleware uncached, reopening the exact leak the fix closes.
    """

    def test_any_header_value_counts_as_inertia(self) -> None:
        scope = {"type": "http", "headers": [(b"x-inertia", b"false")]}

        assert is_inertia_request(scope) is True

    async def test_a_non_true_value_still_gets_the_safety_headers(self) -> None:
        """A route that mirrors upstream's own (presence-only) detection.

        Unlike ``cache_client``'s app, this handler does not call
        ``is_inertia_request`` itself — it reproduces upstream's check
        directly, so the two are genuinely independent here.
        """

        async def page(request):
            if "x-inertia" in request.headers:
                response = JSONResponse({"component": "Home", "props": {}})
            else:
                response = HTMLResponse("<!DOCTYPE html><title>Page</title>")
            response.headers["Cache-Control"] = _PUBLIC_CACHE
            response.headers["ETag"] = _SHARED_ETAG
            return response

        app = Starlette(routes=[Route("/p/home", page)])
        app.add_middleware(InertiaCacheMiddleware)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/p/home", headers={"X-Inertia": "false"})

        assert resp.headers["content-type"].startswith("application/json")
        assert resp.headers["cache-control"] == PAYLOAD_CACHE_CONTROL
        assert "etag" not in resp.headers


class TestDocumentResponse:
    async def test_document_varies_on_x_inertia(self, cache_client: httpx.AsyncClient) -> None:
        """Otherwise a cached document can be served to a client-side visit."""
        async with cache_client as client:
            resp = await client.get("/p/home")

        assert "x-inertia" in _vary_fields(resp)

    async def test_document_keeps_the_caching_the_route_chose(
        self, cache_client: httpx.AsyncClient
    ) -> None:
        """Public page content stays cacheable — that half was never the bug."""
        async with cache_client as client:
            resp = await client.get("/p/home")

        assert resp.headers["cache-control"] == _PUBLIC_CACHE
        assert resp.headers["etag"] == _SHARED_ETAG


class TestUnrelatedResponses:
    async def test_static_assets_are_untouched(self, cache_client: httpx.AsyncClient) -> None:
        """Adding Vary or dropping ETags here would cost every asset its 304."""
        async with cache_client as client:
            resp = await client.get("/static/app.css")

        assert resp.headers["etag"] == _SHARED_ETAG
        assert "x-inertia" not in _vary_fields(resp)


class TestAgainstTheRealApp:
    async def test_a_rendered_view_never_returns_a_storable_payload(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """End to end, through the whole middleware pipeline."""
        resp = await authenticated_client.get("/dashboard/", headers=_INERTIA)

        assert resp.status_code == _OK
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.headers["cache-control"] == PAYLOAD_CACHE_CONTROL
        assert "x-inertia" in _vary_fields(resp)
