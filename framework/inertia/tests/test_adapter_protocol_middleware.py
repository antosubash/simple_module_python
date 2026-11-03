"""Pure ASGI protocol checks, including message-level streaming guarantees."""

import pytest
from starlette.datastructures import Headers


async def _exchange(start, bodies, *, method="POST", headers=()):
    from simple_module_inertia import InertiaMiddleware

    sent = []

    async def downstream(scope, receive, send):
        await send(start)
        # A known non-empty body must not delay the start message.
        if int(Headers(raw=start["headers"]).get("content-length", "0")) > 0:
            assert sent
        for body in bodies:
            await send(body)
            # Every streaming chunk reaches the caller before the next is made.
            if body.get("more_body"):
                assert sent[-1] == body

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message.copy())

    scope = {
        "type": "http",
        "method": method,
        "scheme": "http",
        "server": ("test", 80),
        "path": "/",
        "query_string": b"",
        "headers": list(headers),
    }
    await InertiaMiddleware(downstream)(scope, receive, send)
    return sent


@pytest.mark.parametrize("status", [200, 302, 307])
async def test_plain_request_is_untouched(status):
    start = {
        "type": "http.response.start",
        "status": status,
        "headers": [(b"location", b"/p#anchor")],
    }
    body = {"type": "http.response.body", "body": b""}
    assert await _exchange(start, [body], method="DELETE") == [start, body]


async def test_prefetch_fragment_redirect_is_untouched():
    start = {"type": "http.response.start", "status": 303, "headers": [(b"location", b"/p#anchor")]}
    sent = await _exchange(
        start,
        [{"type": "http.response.body", "body": b""}],
        headers=[(b"x-inertia", b"true"), (b"purpose", b"prefetch")],
    )
    assert sent[0]["status"] == 303
    assert Headers(raw=sent[0]["headers"])["location"] == "/p#anchor"


@pytest.mark.parametrize("first", [b"", b"chunk"])
async def test_streaming_200_is_untouched_even_if_first_chunk_is_empty(first):
    start = {"type": "http.response.start", "status": 200, "headers": []}
    bodies = [
        {"type": "http.response.body", "body": first, "more_body": True},
        {"type": "http.response.body", "body": b"tail"},
    ]
    sent = await _exchange(start, bodies, headers=[(b"x-inertia", b"true")])
    assert sent[0]["status"] == 200
    assert sent[1:] == bodies


async def test_known_nonempty_200_sends_start_immediately():
    start = {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-length", b"10000")],
    }
    bodies = [{"type": "http.response.body", "body": b"x" * 10000}]
    sent = await _exchange(start, bodies, headers=[(b"x-inertia", b"true")])
    assert sent[0]["status"] == 200
    assert sent[1:] == bodies


@pytest.mark.parametrize(
    "headers,expected",
    [
        (
            [(b"content-type", b"text/html; charset=utf-8"), (b"vary", b"Accept")],
            "Accept, X-Inertia",
        ),
        ([(b"content-type", b"text/html"), (b"vary", b"accept, x-inertia")], "accept, x-inertia"),
        ([(b"x-inertia", b"true")], "X-Inertia"),
    ],
)
async def test_vary_preserves_fields_and_deduplicates(headers, expected):
    start = {"type": "http.response.start", "status": 200, "headers": headers}
    sent = await _exchange(start, [{"type": "http.response.body", "body": b"page"}])
    assert Headers(raw=sent[0]["headers"])["vary"] == expected


async def test_fragment_redirect_discards_streamed_body_but_keeps_cookie():
    start = {
        "type": "http.response.start",
        "status": 302,
        "headers": [
            (b"location", b"/p#a"),
            (b"set-cookie", b"session=abc"),
            (b"content-length", b"4"),
        ],
    }
    sent = await _exchange(
        start, [{"type": "http.response.body", "body": b"body"}], headers=[(b"x-inertia", b"true")]
    )
    assert sent[0]["status"] == 409
    headers = Headers(raw=sent[0]["headers"])
    assert headers["x-inertia-redirect"] == "/p#a"
    assert headers["set-cookie"] == "session=abc"
    assert headers["content-length"] == "0"
    assert sent[1:] == [{"type": "http.response.body", "body": b""}]


@pytest.mark.parametrize("length", [None, "0", "00"])
async def test_empty_200_redirects_after_the_first_body_message(length):
    headers = [] if length is None else [(b"content-length", length.encode())]
    start = {"type": "http.response.start", "status": 200, "headers": headers}
    sent = await _exchange(
        start,
        [{"type": "http.response.body", "body": b""}],
        headers=[(b"x-inertia", b"true"), (b"referer", b"/before")],
    )
    assert sent[0]["status"] == 303
    assert Headers(raw=sent[0]["headers"])["location"] == "/before"
    assert sent[1]["body"] == b""
