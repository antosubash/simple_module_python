"""Relative conflicts, complete Vary headers and safe HTML/session boundaries (#1082)."""

import json
from types import SimpleNamespace

import pytest
from fastapi.templating import Jinja2Templates
from simple_module_inertia import Inertia, InertiaConfig, InertiaVersionConflictException
from simple_module_inertia._json_snapshot import JsonSnapshot, dumps
from simple_module_inertia.middleware import add_vary
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
