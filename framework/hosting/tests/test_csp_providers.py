"""CSP providers follow runtime state instead of freezing at boot (#434).

``register_csp_sources`` runs before DB settings hydrate, so an origin that
comes from a setting (a configurable tile server, an analytics host) cannot be
a static ``add()``. A provider is evaluated per response against ``app``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import pytest
import simple_module_hosting.app_builder as app_builder
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.csp import CspSourceRegistry
from simple_module_hosting.middleware import SecurityHeadersMiddleware
from simple_module_test.fixtures import _build_app
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

_CSP = "content-security-policy"


class TilesModule(ModuleBase):
    """Reads its tile origin from (DB-hydrated) settings on ``app.state``."""

    meta = ModuleMeta(name="CspTiles")

    def register_settings(self, app) -> None:
        app.state.csptiles = SimpleNamespace(tile_origin="https://tiles-a.example")

    def register_csp_sources(self, registry: CspSourceRegistry) -> None:
        registry.add_provider(lambda app: [("img-src", app.state.csptiles.tile_origin)])


@pytest.fixture
async def tiles_app(monkeypatch, settings):
    real_discover = app_builder.discover_modules
    monkeypatch.setattr(
        app_builder, "discover_modules", lambda *a, **k: [*real_discover(*a, **k), TilesModule()]
    )
    async for application in _build_app(settings, seed_admin=True):
        yield application


async def _csp(app, path: str = "/health/live") -> str:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        resp = await c.get(path)
    return resp.headers[_CSP]


class TestThroughCreateApp:
    async def test_provider_origin_reaches_real_response(self, tiles_app) -> None:
        assert "https://tiles-a.example" in await _csp(tiles_app)

    async def test_changed_setting_changes_next_response(self, tiles_app) -> None:
        await _csp(tiles_app)
        tiles_app.state.csptiles.tile_origin = "https://tiles-b.example"
        csp = await _csp(tiles_app)
        assert "https://tiles-b.example" in csp
        assert "https://tiles-a.example" not in csp


def _app(
    registry: CspSourceRegistry | None,
    state: dict | None = None,
    csp: str = SecurityHeadersMiddleware.DEFAULT_CSP,
) -> Starlette:
    async def ok(_request):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/", ok)])
    for k, v in (state or {}).items():
        setattr(inner.state, k, v)
    inner.add_middleware(
        SecurityHeadersMiddleware,
        content_security_policy=csp,
        csp_registry=registry,
    )
    return inner


class TestMiddleware:
    async def test_no_providers_header_identical_to_static(self) -> None:
        reg = CspSourceRegistry()
        reg.add("style-src", "https://rsms.me")
        assert await _csp(_app(None), "/") == SecurityHeadersMiddleware.DEFAULT_CSP
        assert await _csp(_app(reg), "/") == SecurityHeadersMiddleware.DEFAULT_CSP

    async def test_raising_provider_leaves_static_policy(self, caplog) -> None:
        reg = CspSourceRegistry()

        def boom(app):
            raise RuntimeError("settings not hydrated")

        reg.add_provider(boom)
        app = _app(reg)
        with caplog.at_level(logging.WARNING):
            assert await _csp(app, "/") == SecurityHeadersMiddleware.DEFAULT_CSP
            assert await _csp(app, "/") == SecurityHeadersMiddleware.DEFAULT_CSP
        # Logged once per distinct failure, not once per response.
        assert sum("settings not hydrated" in r.getMessage() for r in caplog.records) == 1

    async def test_invalid_pair_dropped_valid_pair_kept(self, caplog) -> None:
        reg = CspSourceRegistry()
        reg.add_provider(
            lambda app: [
                ("default-src", "*"),
                ("img-src", "https://x; script-src *"),
                ("img-src", "https://ok.example"),
            ]
        )
        with caplog.at_level(logging.WARNING):
            csp = await _csp(_app(reg), "/")
        assert "https://ok.example" in csp
        assert "script-src *" not in csp
        assert "default-src 'self';" in csp
        assert any("default-src" in r.getMessage() for r in caplog.records)

    async def test_only_invalid_pairs_leave_static_policy(self) -> None:
        reg = CspSourceRegistry()
        reg.add_provider(lambda app: [("img-src", "")])
        assert await _csp(_app(reg), "/") == SecurityHeadersMiddleware.DEFAULT_CSP

    async def test_static_sources_kept_alongside_provider_sources(self) -> None:
        reg = CspSourceRegistry()
        reg.add("style-src", "https://rsms.me")
        reg.add_provider(lambda app: [("connect-src", app.state.api)])
        base = reg.extend_policy(SecurityHeadersMiddleware.DEFAULT_CSP)
        csp = await _csp(_app(reg, {"api": "https://api.example"}, base), "/")
        assert "https://rsms.me" in csp
        assert "connect-src 'self' https://api.example" in csp

    @pytest.mark.parametrize(
        "source",
        [
            "https://exämple.com",
            "https://x.example\x00",
            "https://x.example\x7f",
            "https://x\u2028y",
        ],
    )
    async def test_unencodable_source_never_breaks_the_response(self, source) -> None:
        # An admin-edited setting is the usual input: a value the header
        # encoder cannot carry must be dropped, not 500 every page — including
        # the settings page needed to correct it.
        reg = CspSourceRegistry()
        reg.add_provider(lambda app: [("img-src", source)])
        assert await _csp(_app(reg), "/") == SecurityHeadersMiddleware.DEFAULT_CSP

    async def test_policy_build_failure_falls_back_to_static(self, monkeypatch) -> None:
        reg = CspSourceRegistry()
        reg.add_provider(lambda app: [("img-src", "https://ok.example")])

        def broken(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(reg, "extend_policy", broken)
        assert await _csp(_app(reg), "/") == SecurityHeadersMiddleware.DEFAULT_CSP
