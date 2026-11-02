"""Responses must be compressed when the client advertises support.

The built frontend ships ~139 KB of CSS and ~490 KB of JS. Uncompressed that
is the dominant cost of a cold page load — far larger than anything on the
server request path. Compression cuts the CSS alone by ~85%.
"""

from __future__ import annotations

import httpx
import pytest

_OK = 200
_GZIP = "gzip"
# Below Starlette's default minimum_size, compression is skipped because the
# gzip framing would cost more than it saves.
_TINY_BODY_BYTES = 100


class TestResponseCompression:
    async def test_large_response_is_gzipped_when_accepted(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(
            "/api/permissions/", headers={"Accept-Encoding": "gzip"}
        )
        assert resp.status_code == _OK
        # httpx transparently decodes, so assert on the header the server set.
        assert resp.headers.get("content-encoding") == _GZIP

    async def test_response_is_not_gzipped_when_not_accepted(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A client that doesn't advertise gzip must still get a usable body."""
        resp = await authenticated_client.get(
            "/api/permissions/", headers={"Accept-Encoding": "identity"}
        )
        assert resp.status_code == _OK
        assert resp.headers.get("content-encoding") != _GZIP
        assert resp.json() is not None

    async def test_compression_does_not_corrupt_the_payload(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The decoded body must match what the uncompressed route returns."""
        compressed = await authenticated_client.get(
            "/api/permissions/", headers={"Accept-Encoding": "gzip"}
        )
        plain = await authenticated_client.get(
            "/api/permissions/", headers={"Accept-Encoding": "identity"}
        )
        assert compressed.json() == plain.json()

    async def test_health_endpoint_still_works(self, client: httpx.AsyncClient) -> None:
        """Small responses fall under the size threshold and pass through."""
        resp = await client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == _OK
        assert resp.json() is not None


class TestCompressionMiddlewareOrder:
    def test_gzip_runs_inside_correlation_id(self, app) -> None:
        """GZip must sit inside CorrelationId/RequestLogging.

        Those two set response headers and read request state; compression is
        a transport concern that should wrap only the response body beneath
        them. Starlette's stack is LIFO, so a middleware added *later* is
        outermost — GZip must therefore appear earlier in user_middleware
        than CorrelationId.
        """
        from simple_module_hosting._observability import CorrelationIdMiddleware
        from starlette.middleware.gzip import GZipMiddleware

        classes = [m.cls for m in app.user_middleware]
        assert GZipMiddleware in classes, "GZipMiddleware is not installed"
        assert classes.index(GZipMiddleware) > classes.index(CorrelationIdMiddleware)


@pytest.mark.parametrize("encoding", ["gzip", "gzip, deflate", "gzip, deflate, br"])
async def test_common_browser_accept_encodings(
    authenticated_client: httpx.AsyncClient, encoding: str
) -> None:
    """Real browsers send several forms; all must yield a valid response."""
    resp = await authenticated_client.get(
        "/api/permissions/", headers={"Accept-Encoding": encoding}
    )
    assert resp.status_code == _OK
    assert resp.json() is not None
