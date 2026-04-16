"""Tests for CSRFMiddleware: unsafe-method rejection and header validation."""

from __future__ import annotations

import pytest
from simple_module_hosting.csrf import CSRFMiddleware


def _scope(method: str, headers: list[tuple[bytes, bytes]] | None = None, session=None) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": "/api/anything",
        "headers": headers or [],
        "state": {},
        "session": session if session is not None else {},
    }


async def _noop_receive():  # pragma: no cover
    return {"type": "http.request", "body": b"", "more_body": False}


async def _unreached_app(scope, receive, send):  # pragma: no cover
    raise AssertionError("inner app must not be reached when CSRF rejects")


class _CapturingSend:
    def __init__(self) -> None:
        self.start_message: dict | None = None

    async def __call__(self, message):
        if message["type"] == "http.response.start":
            self.start_message = message


class TestCSRFMiddleware:
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE"])
    async def test_safe_methods_pass_through(self, method: str) -> None:
        """GET/HEAD/OPTIONS/TRACE must never be rejected."""
        calls = {"inner": 0}

        async def inner(scope, receive, send):
            calls["inner"] += 1

        mw = CSRFMiddleware(inner)
        await mw(_scope(method, session={}), _noop_receive, _CapturingSend())
        assert calls["inner"] == 1

    async def test_post_without_session_is_rejected(self) -> None:
        """POST with no session (should never happen behind SessionMiddleware) fails closed."""
        mw = CSRFMiddleware(_unreached_app)
        send = _CapturingSend()
        await mw({**_scope("POST"), "session": {}}, _noop_receive, send)
        assert send.start_message is not None
        assert send.start_message["status"] == 403

    async def test_post_with_mismatched_token_is_rejected(self) -> None:
        send = _CapturingSend()
        mw = CSRFMiddleware(_unreached_app)
        await mw(
            _scope(
                "POST",
                headers=[(b"x-csrf-token", b"wrong")],
                session={"csrf_token": "expected"},
            ),
            _noop_receive,
            send,
        )
        assert send.start_message is not None
        assert send.start_message["status"] == 403

    async def test_post_with_matching_header_passes(self) -> None:
        calls = {"inner": 0}

        async def inner(scope, receive, send):
            calls["inner"] += 1

        mw = CSRFMiddleware(inner)
        await mw(
            _scope(
                "POST",
                headers=[(b"x-csrf-token", b"expected")],
                session={"csrf_token": "expected"},
            ),
            _noop_receive,
            _CapturingSend(),
        )
        assert calls["inner"] == 1

    async def test_accepts_x_xsrf_token_alias(self) -> None:
        """Accept the axios-default header name as well."""
        calls = {"inner": 0}

        async def inner(scope, receive, send):
            calls["inner"] += 1

        mw = CSRFMiddleware(inner)
        await mw(
            _scope(
                "POST",
                headers=[(b"x-xsrf-token", b"expected")],
                session={"csrf_token": "expected"},
            ),
            _noop_receive,
            _CapturingSend(),
        )
        assert calls["inner"] == 1

    async def test_exempt_prefix_bypasses_check(self) -> None:
        """Exempt prefixes should skip validation entirely."""
        calls = {"inner": 0}

        async def inner(scope, receive, send):
            calls["inner"] += 1

        mw = CSRFMiddleware(inner, exempt_path_prefixes=("/api/anything",))
        await mw(_scope("POST", session={}), _noop_receive, _CapturingSend())
        assert calls["inner"] == 1
