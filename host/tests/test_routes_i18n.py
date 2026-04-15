"""Tests for the locale-switcher endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from host.routes_i18n import router as i18n_router


def _build_app(supported: list[str]) -> FastAPI:
    app = FastAPI()
    app.state.settings_supported_locales = supported
    app.state.settings_cookie_name = "locale"
    app.include_router(i18n_router)
    return app


def test_sets_cookie_on_valid_locale() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "/dashboard"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    cookie = resp.cookies.get("locale")
    assert cookie == "es"


def test_rejects_unsupported_locale() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post("/i18n/set-locale", data={"locale": "de"})
    assert resp.status_code == 422


def test_redirects_to_root_when_no_referer() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post("/i18n/set-locale", data={"locale": "es"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_rejects_off_origin_referer() -> None:
    """Attacker-controlled Referer must not become an open redirect."""
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "https://evil.example/steal"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_rejects_protocol_relative_referer() -> None:
    """Protocol-relative Referer (``//evil.example``) must not escape origin."""
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "//evil.example/path"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_accepts_same_origin_absolute_referer() -> None:
    """Absolute Referer matching the request's origin is preserved."""
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    # TestClient's default base is http://testserver/ — match that.
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "http://testserver/products?q=pen"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/products?q=pen"


def test_rejects_relative_referer_without_leading_slash() -> None:
    """Malformed relative Referer without leading slash falls back to ``/``."""
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "not-a-path"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
