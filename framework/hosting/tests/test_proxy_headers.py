"""Proxy-header handling (X-Forwarded-Proto / X-Forwarded-For).

Behind a TLS-terminating reverse proxy the app sees plain ``http`` on the
container socket and the proxy's own address as the client, so
``request.url.scheme`` and ``request.client`` are both wrong.

When ``SM_TRUSTED_PROXY`` is set, the host registers uvicorn's
``ProxyHeadersMiddleware`` as the outermost middleware so the corrected scheme
and client IP are visible to every downstream middleware (logging included).
Left unset (the default) nothing changes — the header is ignored.

This used to be the *only* thing standing between a proxied install and a
broken UI, because inertia-python copies the scheme into the page object's
absolute ``url`` and the browser then refuses the cross-scheme
``history.pushState`` (GH #223). The page url is root-relative now, so that
coupling is gone and ``TestSchemeCorrection`` asserts its absence.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from simple_module_test.fixtures import _create_all_tables, _seed_setup_admin

_LOGIN_PATH = "/users/login"


def _names(app) -> tuple[str, ...]:
    return tuple(m.cls.__name__ for m in app.user_middleware)


def _settings(**overrides) -> Settings:
    base = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "environment": "testing",
        "secret_key": "x" * 32,
        "multi_tenant": False,
    }
    base.update(overrides)
    return Settings(**base)


class TestMiddlewareWiring:
    def test_absent_by_default(self) -> None:
        """No SM_TRUSTED_PROXY → ProxyHeadersMiddleware must not be installed."""
        app = create_app(_settings())
        assert "ProxyHeadersMiddleware" not in _names(app)

    def test_present_and_outermost_when_configured(self) -> None:
        """ProxyHeaders must run before every other middleware.

        ``app.user_middleware`` is in execution order (FastAPI reverses the
        LIFO add_middleware stack), so the proxy middleware must be first —
        otherwise RequestLogging would log the proxy's address, and every
        layer below it would read the uncorrected scheme.
        """
        app = create_app(_settings(trusted_proxy="*"))
        names = _names(app)
        assert names[0] == "ProxyHeadersMiddleware"

    def test_trusted_hosts_passed_through(self) -> None:
        """The configured value reaches uvicorn's middleware as trusted_hosts."""
        app = create_app(_settings(trusted_proxy="10.0.0.0/8,127.0.0.1"))
        proxy = next(m for m in app.user_middleware if m.cls.__name__ == "ProxyHeadersMiddleware")
        assert proxy.kwargs["trusted_hosts"] == "10.0.0.0/8,127.0.0.1"

    def test_surrounding_whitespace_stripped(self) -> None:
        """A stray space must not silently defeat ``*`` trust.

        uvicorn computes always-trust as ``raw in ("*", ["*"])`` *before*
        stripping, so ``"* "`` would be parsed as a literal host that never
        matches any client — silently re-introducing GH #223 with no error.
        The setting must normalize the value first.
        """
        app = create_app(_settings(trusted_proxy="* "))
        proxy = next(m for m in app.user_middleware if m.cls.__name__ == "ProxyHeadersMiddleware")
        assert proxy.kwargs["trusted_hosts"] == "*"

    def test_blank_value_disables(self) -> None:
        """Whitespace-only SM_TRUSTED_PROXY is treated as unset (no middleware)."""
        app = create_app(_settings(trusted_proxy="   "))
        assert "ProxyHeadersMiddleware" not in _names(app)


async def _client_for(settings: Settings):
    """Build an app + lifespan-started client mirroring the shared fixtures."""
    app = create_app(settings)
    await _create_all_tables(app.state.sm.db.engine)
    # Without an administrator the setup gate redirects every request to
    # /setup, including the login page these tests assert on.
    await _seed_setup_admin(app)
    ctx = app.router.lifespan_context(app)
    await ctx.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client, ctx


class TestSchemeCorrection:
    @pytest.mark.parametrize("trusted_proxy", ["*", None])
    async def test_the_inertia_page_url_carries_no_scheme(self, trusted_proxy: str | None) -> None:
        """The page object's url is relative, so no scheme can be wrong.

        This used to be the thing the browser chokes on: upstream sets
        ``"url": str(request.url)``, scheme included, and embeds it in the
        ``data-page`` blob of the rendered HTML, so an install that had not set
        ``SM_TRUSTED_PROXY`` shipped ``http://…`` to an ``https://`` document
        and every ``pushState`` threw (GH #223).

        The url is now root-relative, as the Inertia protocol specifies, and
        the proxy setting is parametrized to show it no longer participates:
        neither spelling can put an origin into the payload.
        """
        client, ctx = await _client_for(_settings(trusted_proxy=trusted_proxy))
        try:
            resp = await client.get(_LOGIN_PATH, headers={"X-Forwarded-Proto": "https"})
            assert resp.status_code == 200
            assert "http://testserver" not in resp.text
            assert "https://testserver" not in resp.text
            assert f'"url": "{_LOGIN_PATH}"' in resp.text
        finally:
            await client.aclose()
            await ctx.__aexit__(None, None, None)
