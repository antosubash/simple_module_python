"""Relative conflicts, complete Vary headers and safe HTML/session boundaries (#1082)."""

import json
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    inertia_dependency_factory,
    inertia_version_conflict_exception_handler,
)
from simple_module_inertia.protocol.middleware import add_vary
from simple_module_inertia.rendering._json_snapshot import JsonSnapshot, dumps
from starlette.datastructures import URL, MutableHeaders
from starlette.requests import Request


@pytest.mark.parametrize("url_type", [str, URL])
@pytest.mark.parametrize("suffix", ["/users", "/users?q=a%20b&next=%2Fhome"])
def test_conflict_location_excludes_proxy_origin(tmp_path, url_type, suffix):
    request = SimpleNamespace(
        url=url_type("http://internal:8000" + suffix),
        method="GET",
        headers={"X-Inertia": "true", "X-Inertia-Version": "old"},
    )
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="new")
    with pytest.raises(InertiaVersionConflictException) as caught:
        Inertia(request, config)
    assert caught.value.url == suffix


@pytest.mark.parametrize(
    "values, expected",
    [
        (["*"], "*"),
        (["Accept", "Cookie, x-inertia", "accept, X-Inertia"], "Accept, Cookie, x-inertia"),
        (["Accept", "Cookie"], "Accept, Cookie, X-Inertia"),
        (["Accept", "*"], "*"),
        (["", "  Cookie , "], "Cookie, X-Inertia"),
    ],
)
def test_vary_combines_all_lines_and_preserves_wildcard(values, expected):
    headers = MutableHeaders(raw=[(b"vary", value.encode()) for value in values])
    add_vary(headers)
    assert headers.getlist("vary") == [expected]


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("snapshot", [False, True])
def test_html_json_rejects_nonfinite_props(number, snapshot):
    messages = JsonSnapshot({"hello": "world"}) if snapshot else {"hello": "world"}
    with pytest.raises(ValueError, match="Out of range float"):
        dumps({"props": {"i18n": {"messages": messages}, "number": number}})


async def test_flash_defaults_without_session_middleware(tmp_path):
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [(b"x-inertia", b"true")]}
    )
    config = InertiaConfig(
        templates=Jinja2Templates(directory=tmp_path),
        version="",
        use_flash_errors=True,
        use_flash_messages=True,
    )
    response = await Inertia(request, config).render("Page")
    assert json.loads(response.body)["props"] == {"errors": {}, "messages": []}


@pytest.mark.parametrize(
    "path, expected",
    [
        ("//evil.example/path", "/%2Fevil.example/path?q=1"),
        ("///evil.example/path", "/%2F/evil.example/path?q=1"),
        ("/%2Fevil.example/path", "/%2Fevil.example/path?q=1"),
        (r"/\evil.example/path", "/%5Cevil.example/path?q=1"),
    ],
)
async def test_stale_catch_all_location_cannot_escape_origin(tmp_path, path, expected):
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="new")
    app = FastAPI()
    app.add_exception_handler(
        InertiaVersionConflictException, inertia_version_conflict_exception_handler
    )

    @app.get("/{path:path}")
    async def page(inertia: Inertia = Depends(inertia_dependency_factory(config))):
        return await inertia.render("Page")

    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        # An absolute URL preserves the path's leading slashes through httpx.
        response = await client.get(
            "https://good.example" + path + "?q=1",
            headers={"X-Inertia": "true", "X-Inertia-Version": "old"},
        )
    assert response.status_code == 409
    target = response.headers["X-Inertia-Location"]
    assert target == expected
    assert not target.startswith(("//", "/\\", "\\"))
    assert urlsplit(urljoin("https://good.example/", target.replace("\\", "/"))).netloc == (
        "good.example"
    )
