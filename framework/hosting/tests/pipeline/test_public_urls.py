"""The account-link fallback accepts only a safe, allowlisted request authority."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._forwarded_host import TRUSTED_PROXY_SCOPE_KEY
from simple_module_hosting.pipeline.public_urls import trusted_request_origin


@pytest.mark.parametrize(
    ("scheme", "authority", "allowlist", "trusted_peer", "expected"),
    [
        ("https", "APP.EXAMPLE", ["app.example"], False, "https://app.example"),
        ("https", "a.b.example", ["*.example"], False, "https://a.b.example"),
        ("https", "example", ["*.example"], False, None),
        ("https", "app.example:444", ["app.example:443"], False, None),
        ("https", "app.example:65536", ["app.example"], False, None),
        ("https", "app.example@other.example", ["*.example"], False, None),
        ("https", "app.example\\@other.example", ["*.example"], False, None),
        ("http", "127.255.0.2:8000", ["127.255.0.2"], False, "http://127.255.0.2:8000"),
        ("http", "127.0.0.1.example", ["127.0.0.1.example"], False, None),
        ("http", "[::1]:8000", ["[::1]"], False, "http://[::1]:8000"),
        ("http", "[::2]", ["[::2]"], False, None),
        ("http", "app.example:8000", ["app.example"], True, "http://app.example:8000"),
        ("ws", "app.example", ["app.example"], True, None),
    ],
)
def test_trusted_request_origin(scheme, authority, allowlist, trusted_peer, expected):
    app = FastAPI()
    app.state.host = SimpleNamespace(settings=HostSettings(forwarded_host_allowlist=allowlist))
    request = Request(
        {
            "type": "http",
            "app": app,
            "scheme": scheme,
            "path": "/irrelevant",
            "query_string": b"token=ignored",
            "headers": [(b"host", authority.encode())],
            TRUSTED_PROXY_SCOPE_KEY: trusted_peer,
        }
    )
    assert trusted_request_origin(request) == expected


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([], "https://app.example"),
        ([(b"host", b"evil.example/path")], None),
        ([(b"host", b"app.example"), (b"host", b"evil.example")], None),
    ],
)
def test_server_authority_is_eligible_only_without_a_conflicting_host(headers, expected):
    app = FastAPI()
    app.state.host = SimpleNamespace(
        settings=HostSettings(forwarded_host_allowlist=["app.example"])
    )
    request = Request(
        {
            "type": "http",
            "app": app,
            "scheme": "https",
            "path": "/",
            "headers": headers,
            "server": ("app.example", 443),
        }
    )

    assert trusted_request_origin(request) == expected
