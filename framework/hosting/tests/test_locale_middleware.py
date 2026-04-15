"""Tests for LocaleMiddleware request-state population."""

from __future__ import annotations

from simple_module_hosting.i18n_middleware import LocaleMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _build_app(supported: list[str], default: str, cookie_name: str = "locale") -> Starlette:
    async def endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"locale": request.state.locale})

    app = Starlette(routes=[Route("/", endpoint)])
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=supported,
        default_locale=default,
        cookie_name=cookie_name,
    )
    return app


def test_uses_cookie_when_present_and_supported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", cookies={"locale": "es"})
    assert resp.json() == {"locale": "es"}


def test_ignores_cookie_when_locale_not_supported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", cookies={"locale": "de"})
    # Falls through to Accept-Language, then to default (en).
    assert resp.json() == {"locale": "en"}


def test_uses_accept_language_when_no_cookie() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", headers={"Accept-Language": "es,en;q=0.8"})
    assert resp.json() == {"locale": "es"}


def test_prefix_match_accept_language() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    # "es-MX" should match supported "es" via prefix.
    resp = client.get("/", headers={"Accept-Language": "es-MX"})
    assert resp.json() == {"locale": "es"}


def test_falls_back_to_default_when_nothing_matches() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", headers={"Accept-Language": "de,fr;q=0.5"})
    assert resp.json() == {"locale": "en"}


def test_cookie_takes_precedence_over_accept_language() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get(
        "/",
        cookies={"locale": "es"},
        headers={"Accept-Language": "de"},
    )
    assert resp.json() == {"locale": "es"}


def test_custom_cookie_name() -> None:
    app = _build_app(["en", "es"], "en", cookie_name="lang")
    client = TestClient(app)
    resp = client.get("/", cookies={"lang": "es"})
    assert resp.json() == {"locale": "es"}
