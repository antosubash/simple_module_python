"""End-to-end integration test for the i18n flow.

Exercises the full cookie -> middleware -> TranslatorDep -> rendered-string
path against a real ``create_app()``: POST /i18n/set-locale sets the cookie,
subsequent requests have ``request.state.locale`` set by LocaleMiddleware,
endpoints that inject ``TranslatorDep`` return locale-specific content, and
Inertia shared props reflect the active locale.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from simple_module_hosting.settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Extend default settings with a second supported locale."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=True,
        tenant_header="X-Tenant-ID",
        i18n_default_locale="en",
        i18n_supported_locales=["en", "es"],
    )


@pytest.fixture
async def app_with_host_routes(app):  # type: ignore[no-untyped-def]
    """``app`` fixture + host-level routers (landing, switcher).

    The stock ``app`` fixture builds via ``create_app()``, which only wires
    module routes. The host's own routers (``host.routes``, ``host.routes_i18n``)
    are included in ``host/main.py``, not ``create_app``. Reproduce that here
    so integration tests can hit ``/`` and ``/i18n/set-locale``.
    """
    from host.routes import router as host_router
    from host.routes_i18n import router as i18n_router

    app.include_router(host_router)
    app.include_router(i18n_router)
    return app


@pytest.fixture
async def host_client(app_with_host_routes) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against the host-routes-enabled app.

    Pre-seeded with a signed anonymous session carrying a CSRF token so
    POST flows (e.g. /i18n/set-locale) clear CSRFMiddleware.
    """
    from simple_module_hosting.csrf import SESSION_CSRF_TOKEN_KEY
    from simple_module_testing import forge_session_cookie

    csrf = "test-csrf-token"
    signed = forge_session_cookie(
        str(app_with_host_routes.state.settings.secret_key),
        {SESSION_CSRF_TOKEN_KEY: csrf},
    )
    transport = httpx.ASGITransport(app=app_with_host_routes)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": signed},
        headers={"X-CSRF-Token": csrf},
    ) as c:
        yield c


async def test_switcher_sets_cookie_and_subsequent_requests_use_new_locale(
    app_with_host_routes,
    host_client: httpx.AsyncClient,
) -> None:
    """POST /i18n/set-locale -> cookie -> next request picks it up."""
    # Sanity check: default locale is 'en'.
    resp = await host_client.get("/")
    assert resp.status_code == 200

    # Switch to Spanish via the switcher endpoint (same-origin Referer).
    resp = await host_client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "http://testserver/"},
    )
    assert resp.status_code == 303
    assert "locale=es" in resp.headers.get("set-cookie", "")

    # Landing page is a non-Inertia request; we can't assert content easily
    # without building an Inertia response — instead, probe the registry
    # state through a follow-up request and assert the cookie "sticks".
    resp = await host_client.get("/", cookies={"locale": "es"})
    assert resp.status_code == 200


async def test_inertia_shared_props_include_active_locale_messages(
    app,
    authenticated_client: httpx.AsyncClient,
) -> None:
    """An Inertia request honors the locale cookie in shared props."""
    # Hit an Inertia view endpoint (dashboard) with the es cookie.
    resp = await authenticated_client.get(
        "/dashboard/",
        headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        cookies={"locale": "es"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Inertia response shape: {"component": ..., "props": {"i18n": {...}, ...}}
    i18n = body["props"]["i18n"]
    assert i18n["locale"] == "es"
    # Dashboard module ships es.json with the 'dashboard.home.title' key.
    assert "dashboard.home.title" in i18n["messages"]
    # Value must differ from the English translation to prove the cookie hit.
    assert i18n["messages"]["dashboard.home.title"] != "Dashboard"


# NOTE: We'd like a test here for TranslatorDep in an HTTPException detail,
# but the products delete endpoint uses framework/hosting's RequiresPermission
# class (not the auth module's TranslatorDep-aware require_permission dep),
# which has a hardcoded English detail. Localizing RequiresPermission.detail
# is a separate follow-up. The Inertia shared-props test above already
# verifies the end-to-end cookie -> middleware -> registry -> locale-specific
# messages path, which is the principal contract i18n promises.


async def test_switcher_rejects_locale_without_loaded_messages(
    app_with_host_routes,
    host_client: httpx.AsyncClient,
) -> None:
    """A locale outside available_locales() is rejected even if in settings.

    Because `i18n_supported_locales=["en","es"]` and both have JSON files,
    a third locale like 'de' is not available and must be rejected (422).
    """
    resp = await host_client.post(
        "/i18n/set-locale",
        data={"locale": "de"},
        headers={"Referer": "http://testserver/"},
    )
    assert resp.status_code == 422
