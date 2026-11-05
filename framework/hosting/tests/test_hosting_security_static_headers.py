"""Static security headers replace all endpoint values without losing other headers."""

import pytest
from simple_module_hosting.middleware import SecurityHeadersMiddleware


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
    assert dict(headers)[b"referrer-policy"] == b"strict-origin-when-cross-origin"
    assert dict(headers)[b"strict-transport-security"] == (
        hsts.encode() if hsts else b"endpoint-value"
    )
