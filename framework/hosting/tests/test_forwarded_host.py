"""X-Forwarded-Host from a trusted proxy, honoured for allowlisted hosts only (#528)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from simple_module_hosting._forwarded_host import (
    ForwardedHostMiddleware,
    HostAllowlist,
    TrustedPeers,
)
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings

_PROBE_PATH = "/forwarded-host-probe"
_PROBE_NAME = "forwarded_host_probe"
_PROXY_IP = "10.1.2.3"
_STRANGER_IP = "198.51.100.9"
_PUBLIC_HOST = "app.example.com"
_FORWARDED = "x-forwarded-host"


def _names(app) -> tuple[str, ...]:
    return tuple(m.cls.__name__ for m in app.user_middleware)


def _settings(**overrides) -> Settings:
    base = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "environment": "testing",
        "secret_key": "x" * 32,
        "multi_tenant": False,
    }
    return Settings(**(base | overrides))


def _probe_app(**middleware) -> FastAPI:
    app = FastAPI()

    @app.get(_PROBE_PATH, name=_PROBE_NAME)
    async def probe(request: Request) -> dict[str, str]:
        return {"url": str(request.url_for(_PROBE_NAME)), "host": request.url.hostname or ""}

    return ForwardedHostMiddleware(app, **middleware)  # ty: ignore[invalid-return-type]


async def _get(app, forwarded: str, *, peer: str = _PROXY_IP) -> dict[str, str]:
    transport = httpx.ASGITransport(app=app, client=(peer, 4242))
    async with httpx.AsyncClient(transport=transport, base_url="http://internal:8000") as client:
        resp = await client.get(_PROBE_PATH, headers={_FORWARDED: forwarded})
    return resp.json()


def _mw(allowlist: list[str], trusted: str = _PROXY_IP):
    return _probe_app(trusted_hosts=trusted, allowlist=allowlist)


class TestWiring:
    def test_absent_by_default(self) -> None:
        assert "ForwardedHostMiddleware" not in _names(create_app(_settings()))

    def test_needs_both_proxy_and_allowlist(self) -> None:
        only_proxy = create_app(_settings(trusted_proxy="*"))
        only_list = create_app(_settings(forwarded_host_allowlist=[_PUBLIC_HOST]))
        assert "ForwardedHostMiddleware" not in _names(only_proxy)
        assert "ForwardedHostMiddleware" not in _names(only_list)

    def test_runs_before_proxy_headers(self) -> None:
        app = create_app(_settings(trusted_proxy="*", forwarded_host_allowlist=[_PUBLIC_HOST]))
        names = _names(app)
        assert names[:2] == ("ForwardedHostMiddleware", "ProxyHeadersMiddleware")


class TestRewrite:
    async def test_allowlisted_host_builds_public_urls(self) -> None:
        body = await _get(_mw([_PUBLIC_HOST]), _PUBLIC_HOST)
        assert body == {"url": f"http://{_PUBLIC_HOST}{_PROBE_PATH}", "host": _PUBLIC_HOST}

    async def test_forged_host_not_on_allowlist_is_ignored(self) -> None:
        body = await _get(_mw([_PUBLIC_HOST]), "evil.example.net")
        assert body["host"] == "internal"

    async def test_untrusted_peer_is_ignored(self) -> None:
        body = await _get(_mw([_PUBLIC_HOST]), _PUBLIC_HOST, peer=_STRANGER_IP)
        assert body["host"] == "internal"

    async def test_leftmost_value_is_used(self) -> None:
        body = await _get(_mw([_PUBLIC_HOST]), f"{_PUBLIC_HOST}, evil.example.net")
        assert body["host"] == _PUBLIC_HOST

    async def test_leftmost_forged_value_is_not_rescued_by_a_later_good_one(self) -> None:
        body = await _get(_mw([_PUBLIC_HOST]), f"evil.example.net, {_PUBLIC_HOST}")
        assert body["host"] == "internal"

    async def test_wildcard_matches_subdomains_not_the_apex(self) -> None:
        mw = _mw(["*.example.com"])
        assert (await _get(mw, "acme.example.com"))["host"] == "acme.example.com"
        assert (await _get(mw, "example.com"))["host"] == "internal"

    async def test_port_is_kept_and_checked(self) -> None:
        mw = _mw([f"{_PUBLIC_HOST}:8443"])
        assert (await _get(mw, f"{_PUBLIC_HOST}:8443"))["url"].startswith(
            f"http://{_PUBLIC_HOST}:8443"
        )
        assert (await _get(mw, f"{_PUBLIC_HOST}:9"))["host"] == "internal"

    @pytest.mark.parametrize("value", ["a b.example.com", "app.example.com/x", "u@app.example.com"])
    async def test_malformed_values_are_ignored(self, value: str) -> None:
        assert (await _get(_mw(["*.example.com"]), value))["host"] == "internal"


class TestPeers:
    @pytest.mark.parametrize(
        ("spec", "peer", "trusted"),
        [
            ("*", _STRANGER_IP, True),
            ("10.0.0.0/8", _PROXY_IP, True),
            ("10.0.0.0/8", _STRANGER_IP, False),
            ("192.0.2.1, 10.1.2.3", _PROXY_IP, True),
            ("10.0.0.0/8", None, False),
        ],
    )
    def test_trusted_hosts_rule(self, spec: str, peer: str | None, trusted: bool) -> None:
        assert (peer in TrustedPeers(spec)) is trusted

    def test_allowlist_skips_invalid_entries(self) -> None:
        assert not HostAllowlist(["bad entry/", ""]).allows("app.example.com", None)
