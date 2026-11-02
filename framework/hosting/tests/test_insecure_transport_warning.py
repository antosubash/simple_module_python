"""A ``Secure`` session cookie served over plain HTTP warns once (#495)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx
import pytest
from simple_module_hosting import _insecure_transport
from simple_module_hosting._insecure_transport import warn_if_plain_http
from simple_module_hosting.session import SessionMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

_LOGGER = "simple_module_hosting.session"


@pytest.fixture(autouse=True)
def _fresh_flag() -> Iterator[None]:
    _insecure_transport._reset_for_tests()
    yield
    _insecure_transport._reset_for_tests()


def _scope(scheme: str, host: str) -> dict:
    return {"type": "http", "scheme": scheme, "headers": [(b"host", host.encode())]}


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING]


def test_plain_http_to_real_host_warns_once_naming_both_settings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warn_if_plain_http(_scope("http", "app.example.com:8000"))
        warn_if_plain_http(_scope("http", "other.example.com"))
    records = _warnings(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert "SM_TRUSTED_PROXY" in message
    assert "SM_SESSION_COOKIE_SECURE" in message


@pytest.mark.parametrize(
    ("scheme", "host"),
    [
        ("https", "app.example.com"),
        ("http", "localhost:8000"),
        ("http", "app.localhost"),
        ("http", "127.0.0.1:8000"),
        ("http", "[::1]:8000"),
    ],
)
def test_https_or_loopback_does_not_warn(
    caplog: pytest.LogCaptureFixture, scheme: str, host: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warn_if_plain_http(_scope(scheme, host))
    assert not _warnings(caplog)
    assert _insecure_transport._warned is False


def _app(*, https_only: bool) -> Starlette:
    async def home(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", home)])
    app.add_middleware(SessionMiddleware, secret_key="k", https_only=https_only)
    return app


@pytest.mark.parametrize(("https_only", "expected"), [(True, 1), (False, 0)])
async def test_session_middleware_warns_only_when_cookie_is_secure(
    caplog: pytest.LogCaptureFixture, https_only: bool, expected: int
) -> None:
    transport = httpx.ASGITransport(app=_app(https_only=https_only))
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        async with httpx.AsyncClient(transport=transport, base_url="http://app.example.com") as c:
            assert (await c.get("/")).status_code == 200
            assert (await c.get("/")).status_code == 200
    assert len(_warnings(caplog)) == expected
