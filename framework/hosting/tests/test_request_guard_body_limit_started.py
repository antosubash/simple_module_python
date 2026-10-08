"""Body guard when the app's response has already started (GH #345 review)."""

from __future__ import annotations

import pytest
from simple_module_hosting._body_limit import BodyLimitMiddleware, _BodyTooLargeError

LIMIT = 1000


async def test_started_response_is_not_swallowed_and_connection_aborts() -> None:
    sent: list[dict] = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        while True:  # streaming echo: keeps reading the request body
            await receive()

    chunks = iter([{"type": "http.request", "body": b"x" * 600, "more_body": True}] * 5)

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/echo",
        "headers": [(b"accept", b"application/json")],
        "query_string": b"",
    }
    with pytest.raises(_BodyTooLargeError):  # the connection is aborted, not left hanging
        await BodyLimitMiddleware(app, max_bytes=LIMIT)(scope, receive, send)
    # What the app had already sent reached the client, and no second (413)
    # response was started on top of it.
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]


async def test_non_ascii_digit_content_length_does_not_500() -> None:
    # "²".isdigit() is True but int("²") raises; that must not become a 500.
    sent: list[dict] = []

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    msgs = iter([{"type": "http.request", "body": b"ok", "more_body": False}])

    async def receive():
        return next(msgs)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/echo",
        "headers": [(b"accept", b"application/json"), (b"content-length", "²".encode("latin-1"))],
        "query_string": b"",
    }
    await BodyLimitMiddleware(app, max_bytes=LIMIT)(scope, receive, send)
    assert sent[0]["status"] == 200
