"""Tests for TranslatorDep end-to-end via a minimal app."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.i18n import I18nRegistry, Translator
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.i18n_middleware import LocaleMiddleware
from starlette.testclient import TestClient


def _build_app() -> FastAPI:
    reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
    reg._messages = {
        "en": {"hello": "Hello, {name}"},
        "es": {"hello": "Hola, {name}"},
    }

    app = FastAPI()

    # Create a mock services object with the needed attributes
    class MockServices:
        def __init__(self, registry, default_locale):
            self.i18n_registry = registry
            self.settings = type("Settings", (), {"i18n_default_locale": default_locale})()

    app.state.sm = MockServices(reg, "en")

    @app.get("/hi")
    def hi(t: TranslatorDep, name: str = "friend") -> dict[str, str]:
        return {"greeting": t.t("hello", name=name), "locale": t.locale}

    app.add_middleware(
        LocaleMiddleware,
        supported_locales=["en", "es"],
        default_locale="en",
    )
    return app


def test_translator_dep_uses_request_locale() -> None:
    client = TestClient(_build_app(), cookies={"locale": "es"})
    resp = client.get("/hi?name=Ana")
    assert resp.json() == {"greeting": "Hola, Ana", "locale": "es"}


def test_translator_dep_falls_back_to_default_locale() -> None:
    client = TestClient(_build_app())
    resp = client.get("/hi?name=Ana")  # no cookie, no Accept-Language
    assert resp.json() == {"greeting": "Hello, Ana", "locale": "en"}


def test_translator_dep_returned_is_translator_instance() -> None:
    app = _build_app()

    @app.get("/type")
    def type_check(t: TranslatorDep) -> dict[str, bool]:
        return {"is_translator": isinstance(t, Translator)}

    client = TestClient(app)
    assert client.get("/type").json() == {"is_translator": True}
