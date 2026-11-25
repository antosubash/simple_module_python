"""Static security headers replace all endpoint values without losing other headers."""

import pytest
from httpx import ASGITransport, AsyncClient
from simple_module_hosting.pipeline.middleware import SecurityHeadersMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route


@pytest.mark.parametrize("hsts", [None, "max-age=123"])
async def test_security_static_headers_replace_duplicates(hsts):
    messages = []

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"x-frame-options", b"DENY"),
                    (b"x-frame-options", b"ALLOWALL"),
                    (b"x-content-type-options", b"endpoint-value"),
                    (b"x-xss-protection", b"endpoint-value"),
                    (b"referrer-policy", b"endpoint-value"),
                    (b"set-cookie", b"a=1"),
                    (b"set-cookie", b"b=2"),
                    (b"strict-transport-security", b"endpoint-value"),
                ],
            }
        )

    async def send(message):
        messages.append(message)

    middleware = SecurityHeadersMiddleware(app, strict_transport_security=hsts)
    await middleware({"type": "http"}, None, send)
    headers = messages[0]["headers"]
    assert [v for k, v in headers if k == b"x-frame-options"] == [b"SAMEORIGIN"]
    assert [v for k, v in headers if k == b"set-cookie"] == [b"a=1", b"b=2"]
    assert dict(headers)[b"x-content-type-options"] == b"nosniff"
    assert dict(headers)[b"x-xss-protection"] == b"0"
    assert dict(headers)[b"referrer-policy"] == b"endpoint-value"
    assert dict(headers)[b"strict-transport-security"] == (
        hsts.encode() if hsts else b"endpoint-value"
    )


@pytest.mark.parametrize(
    ("route_policy", "expected"),
    [(None, "strict-origin-when-cross-origin"), ("no-referrer", "no-referrer")],
)
async def test_referrer_policy_defaults_only_when_absent(route_policy, expected):
    async def page(request):
        headers = {"Referrer-Policy": route_policy} if route_policy else None
        return PlainTextResponse("page", headers=headers)

    app = SecurityHeadersMiddleware(Starlette(routes=[Route("/", page)]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.headers.get_list("referrer-policy") == [expected]


async def test_referrer_policy_default_skipped_on_not_modified():
    """A 304 must not replace the policy the cached 200 carried."""

    async def page(request):
        return Response(status_code=304)

    app = SecurityHeadersMiddleware(Starlette(routes=[Route("/", page)]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 304
    assert "referrer-policy" not in response.headers
