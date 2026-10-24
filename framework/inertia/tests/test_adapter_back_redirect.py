"""``back()`` and the validation handler only redirect within this site (#635)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.errors import inertia_request_validation_exception_handler
from simple_module_inertia.inertia import Inertia
from starlette.requests import Request

OFFSITE = [
    "https://evil.example/",
    "https://evil.example/users/add",
    "//evil.example/users/add",
    "/\\evil.example",
    "http://app.test.evil.example/x",
    "javascript:alert(1)",
    "/users\r\nSet-Cookie: x=1",
]


def _request(referer: str | None) -> Request:
    headers = [(b"host", b"app.test"), (b"x-inertia", b"true")]
    if referer is not None:
        headers.append((b"referer", referer.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "https",
        "server": ("app.test", 443),
        "path": "/users",
        "query_string": b"",
        "headers": headers,
        "app": FastAPI(),
        "session": {},
    }
    return Request(scope)


async def _validation_redirect(referer: str | None) -> str:
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "invalid"}])
    resp = await inertia_request_validation_exception_handler(_request(referer), exc)
    return resp.headers["location"]


def _back(referer: str | None) -> str:
    return Inertia(_request(referer), InertiaConfig(templates=None)).back().headers["location"]


@pytest.mark.parametrize("referer", OFFSITE)
async def test_offsite_referers_fall_back_to_root(referer: str) -> None:
    assert await _validation_redirect(referer) == "/"
    assert _back(referer) == "/"


@pytest.mark.parametrize(
    ("referer", "expected"),
    [
        ("https://app.test/users/add?step=2", "/users/add?step=2"),
        ("http://app.test/users/add", "/users/add"),
        ("https://APP.test:443/users/add", "/users/add"),
        ("/users/add", "/users/add"),
        (None, "/"),
    ],
)
async def test_same_site_referers_are_kept_as_paths(referer: str | None, expected: str) -> None:
    assert await _validation_redirect(referer) == expected
    assert _back(referer) == expected
