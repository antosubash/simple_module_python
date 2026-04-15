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

    app = FastAPI()
    app.state.i18n_registry = reg

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
    client = TestClient(_build_app())
    resp = client.get("/shared", cookies={"locale": "es"})
    body = resp.json()
    assert body["i18n"]["locale"] == "es"
    assert body["i18n"]["messages"] == {"hello": "Hola"}


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
