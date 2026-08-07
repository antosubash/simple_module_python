"""Verify InertiaLayoutDataMiddleware injects an i18n block into shared props."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.i18n import I18nRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.i18n_middleware import LocaleMiddleware
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def _build_app() -> FastAPI:
    reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
    reg._messages = {
        "en": {"hello": "Hello"},
        "es": {"hello": "Hola"},
    }

    from types import SimpleNamespace

    app = FastAPI()
    app.state.sm = SimpleNamespace(i18n_registry=reg)

    @app.get("/shared")
    def shared(request: Request) -> JSONResponse:
        return JSONResponse(request.state.inertia_shared)

    # Stack order (last added = outermost = runs first):
    #   LocaleMiddleware (outer) -> InertiaLayoutDataMiddleware (inner)
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=["en", "es"],
        default_locale="en",
    )
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


def test_inertia_shared_props_include_i18n_block_for_default_locale() -> None:
    client = TestClient(_build_app())
    resp = client.get("/shared")
    body = resp.json()
    assert "i18n" in body
    assert body["i18n"]["locale"] == "en"
    assert body["i18n"]["supportedLocales"] == ["en", "es"]
    assert body["i18n"]["messages"] == {"hello": "Hello"}


def test_inertia_shared_props_reflect_cookie_locale() -> None:
    client = TestClient(_build_app(), cookies={"locale": "es"})
    resp = client.get("/shared")
    body = resp.json()
    assert body["i18n"]["locale"] == "es"
    assert body["i18n"]["messages"] == {"hello": "Hola"}


def _build_audience_app(tmp_path) -> FastAPI:
    """App with a *loaded* registry (public + admin sources) and header-driven auth.

    ``X-Test-Auth: 1`` marks the request authenticated, so one client session
    can flip auth state mid-session — the login/logout transition the i18n
    block must react to.
    """
    import json
    from types import SimpleNamespace

    for ns, data in (
        ("pages", {"title": "Pages"}),
        ("settings", {"key": "Key"}),
    ):
        (tmp_path / ns).mkdir(exist_ok=True)
        (tmp_path / ns / "en.json").write_text(json.dumps(data))
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg.add_source("pages", tmp_path / "pages")
    reg.add_source("settings", tmp_path / "settings", audience="admin")
    reg.load()

    app = FastAPI()
    app.state.sm = SimpleNamespace(i18n_registry=reg)

    @app.get("/shared")
    def shared(request: Request) -> JSONResponse:
        return JSONResponse(request.state.inertia_shared)

    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=["en"],
        default_locale="en",
    )

    class _HeaderAuth:
        def __init__(self, app_):
            self.app = app_

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                request = Request(scope)
                if request.headers.get("X-Test-Auth") == "1":
                    request.state.user = SimpleNamespace(roles=[])
            await self.app(scope, receive, send)

    app.add_middleware(_HeaderAuth)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


def test_anonymous_visitors_receive_only_public_catalogs(tmp_path) -> None:
    client = TestClient(_build_audience_app(tmp_path))
    body = client.get("/shared").json()
    assert body["i18n"]["messages"] == {"pages.title": "Pages"}


def test_authenticated_users_receive_admin_catalogs_too(tmp_path) -> None:
    client = TestClient(_build_audience_app(tmp_path))
    body = client.get("/shared", headers={"X-Test-Auth": "1"}).json()
    assert body["i18n"]["messages"] == {"pages.title": "Pages", "settings.key": "Key"}


def test_login_mid_session_reships_messages_on_an_inertia_partial(tmp_path) -> None:
    """An Inertia partial normally skips messages — but not right after login,
    or the freshly-authenticated client would keep the anonymous catalog."""
    client = TestClient(_build_audience_app(tmp_path))
    client.get("/shared")  # anonymous full load seeds the session audience
    body = client.get("/shared", headers={"X-Test-Auth": "1", "X-Inertia": "true"}).json()
    assert body["i18n"]["messages"] == {"pages.title": "Pages", "settings.key": "Key"}


def test_inertia_partial_with_unchanged_audience_still_skips_messages(tmp_path) -> None:
    client = TestClient(_build_audience_app(tmp_path))
    client.get("/shared")
    body = client.get("/shared", headers={"X-Inertia": "true"}).json()
    assert body["i18n"]["messages"] is None


def test_inertia_shared_props_fallback_when_registry_missing(
    caplog,
) -> None:
    """When app.state.i18n_registry is absent, the middleware logs a warning and
    falls back to a minimal i18n block so tests / misconfigured apps don't crash.
    """
    import logging

    app = FastAPI()
    # Intentionally do NOT set app.state.i18n_registry.

    @app.get("/shared")
    def shared(request: Request) -> JSONResponse:
        return JSONResponse(request.state.inertia_shared)

    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )
    # No LocaleMiddleware either — request.state.locale also absent.
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    with caplog.at_level(logging.WARNING, logger="simple_module_hosting.middleware"):
        client = TestClient(app)
        resp = client.get("/shared")

    body = resp.json()
    assert body["i18n"] == {"locale": "en", "supportedLocales": ["en"], "messages": {}}
    # Fallback must be loud enough to surface misconfigurations:
    assert any("not fully wired" in rec.message for rec in caplog.records)
