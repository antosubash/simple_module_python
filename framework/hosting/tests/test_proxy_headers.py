"""Proxy-header handling (X-Forwarded-Proto / X-Forwarded-For).

Behind a TLS-terminating reverse proxy the app sees plain ``http`` on the
container socket, so ``request.url.scheme`` is wrong. inertia-python copies
that scheme into the page object's absolute ``url``; the browser then refuses
the cross-scheme ``history.pushState`` and login breaks (GH #223).

When ``SM_TRUSTED_PROXY`` is set, the host registers uvicorn's
``ProxyHeadersMiddleware`` as the outermost middleware so the corrected scheme
and client IP are visible to every downstream middleware (logging included).
Left unset (the default) nothing changes — the header is ignored.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from simple_module_test.fixtures import _create_all_tables

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
        otherwise RequestLogging would log the proxy's address, and Inertia
        would already have read the wrong scheme.
        """
        app = create_app(_settings(trusted_proxy="*"))
        names = _names(app)
        assert names[0] == "ProxyHeadersMiddleware"

    def test_trusted_hosts_passed_through(self) -> None:
        """The configured value reaches uvicorn's middleware as trusted_hosts."""
        app = create_app(_settings(trusted_proxy="10.0.0.0/8,127.0.0.1"))
        proxy = next(m for m in app.user_middleware if m.cls.__name__ == "ProxyHeadersMiddleware")
        assert proxy.kwargs["trusted_hosts"] == "10.0.0.0/8,127.0.0.1"


async def _client_for(settings: Settings):
    """Build an app + lifespan-started client mirroring the shared fixtures."""
    app = create_app(settings)
    await _create_all_tables(app.state.sm.db.engine)
    ctx = app.router.lifespan_context(app)
    await ctx.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client, ctx


class TestSchemeCorrection:
    @pytest.mark.parametrize(
        ("trusted_proxy", "expected_scheme"),
        [
            ("*", "https"),  # trusted proxy → X-Forwarded-Proto honored
            (None, "http"),  # no trust configured → header ignored
        ],
    )
    async def test_inertia_page_url_scheme(
        self, trusted_proxy: str | None, expected_scheme: str
    ) -> None:
        """The Inertia page object's absolute url reflects X-Forwarded-Proto.

        This is the exact thing the browser chokes on: inertia-python sets
        ``"url": str(request.url)``, scheme included, and embeds it in the
        ``data-page`` blob of the rendered HTML.
        """
        client, ctx = await _client_for(_settings(trusted_proxy=trusted_proxy))
        try:
            resp = await client.get(_LOGIN_PATH, headers={"X-Forwarded-Proto": "https"})
            assert resp.status_code == 200
            assert f"{expected_scheme}://testserver{_LOGIN_PATH}" in resp.text
            wrong = "https" if expected_scheme == "http" else "http"
            assert f"{wrong}://testserver{_LOGIN_PATH}" not in resp.text
        finally:
            await client.aclose()
            await ctx.__aexit__(None, None, None)
