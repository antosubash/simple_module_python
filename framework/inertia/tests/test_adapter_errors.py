from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from simple_module_inertia.errors import (
    InertiaVersionConflictException,
    inertia_request_validation_exception_handler,
    inertia_version_conflict_exception_handler,
)
from starlette.requests import Request


def _request(headers: dict[str, str], method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "app": FastAPI(),
        "session": {},
    }
    return Request(scope)


async def test_version_conflict_handler_returns_409_with_location() -> None:
    resp = await inertia_version_conflict_exception_handler(
        _request({}), InertiaVersionConflictException(url="http://h/admin/")
    )
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "http://h/admin/"


async def test_validation_errors_are_flashed_and_redirected_back() -> None:
    req = _request({"X-Inertia": "true", "Referer": "/users/add"})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "invalid"}])
    resp = await inertia_request_validation_exception_handler(req, exc)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/users/add"
    assert req.session["_errors"] == {"email": "invalid"}


async def test_error_bag_scopes_the_flashed_errors() -> None:
    req = _request({"X-Inertia": "true", "X-Inertia-Error-Bag": "signup", "Referer": "/"})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "taken"}])
    await inertia_request_validation_exception_handler(req, exc)
    assert req.session["_errors"] == {"signup": {"email": "taken"}}


async def test_non_inertia_validation_errors_keep_fastapis_422() -> None:
    req = _request({})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "invalid"}])
    resp = await inertia_request_validation_exception_handler(req, exc)
    assert resp.status_code == 422
