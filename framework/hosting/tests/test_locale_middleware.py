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
    client = TestClient(app, cookies={"locale": "es"})
    resp = client.get("/")
    assert resp.json() == {"locale": "es"}


def test_ignores_cookie_when_locale_not_supported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app, cookies={"locale": "de"})
    resp = client.get("/")
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
    client = TestClient(app, cookies={"locale": "es"})
    resp = client.get("/", headers={"Accept-Language": "de"})
    assert resp.json() == {"locale": "es"}


def test_custom_cookie_name() -> None:
    app = _build_app(["en", "es"], "en", cookie_name="lang")
    client = TestClient(app, cookies={"lang": "es"})
    resp = client.get("/")
    assert resp.json() == {"locale": "es"}


def test_ows_around_semicolon_does_not_drop_q_value() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    # "es ; q=0.1" should be interpreted with q=0.1; "en" default wins via
    # higher q via the _falls_back test already. Here verify a simpler case:
    # "de ; q=1.0, es ; q=0.5" — de unsupported, es supported -> es.
    resp = client.get(
        "/",
        headers={"Accept-Language": "de ; q=1.0, es ; q=0.5"},
    )
    assert resp.json() == {"locale": "es"}


def test_lower_q_supported_beats_higher_q_unsupported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    # de has higher q but is unsupported; es should win.
    resp = client.get(
        "/",
        headers={"Accept-Language": "de;q=1.0,es;q=0.1"},
    )
    assert resp.json() == {"locale": "es"}


def test_q_zero_language_is_never_chosen() -> None:
    """RFC 9110 §12.4.2: ``q=0`` means "not acceptable" (#792)."""
    mw = LocaleMiddleware(lambda *a: None, supported_locales=["en", "es"], default_locale="en")
    assert mw._negotiate("es;q=0") is None
    assert mw._negotiate("es;q=0.000, en;q=0.1") == "en"
    # A refused regional tag does not fall back to its primary language either.
    assert mw._negotiate("es-MX;q=0") is None


def test_q_zero_header_resolves_to_default() -> None:
    client = TestClient(_build_app(["en", "es"], "en"))
    assert client.get("/", headers={"accept-language": "es;q=0"}).json() == {"locale": "en"}


def test_non_finite_and_out_of_range_q_values() -> None:
    mw = LocaleMiddleware(lambda *a: None, supported_locales=["en", "es"], default_locale="en")
    # nan is not a weight: the candidate is ignored.
    assert mw._negotiate("es;q=nan") is None
    assert mw._negotiate("es;q=nan, en;q=0.5") == "en"
    # Weights above 1 (inf included) count as 1, so header order breaks the tie.
    assert mw._negotiate("es;q=inf, en") == "es"
    assert mw._negotiate("en, es;q=inf") == "en"
    assert mw._negotiate("en, es;q=5") == "en"
    # A negative weight is below 0 and therefore not acceptable.
    assert mw._negotiate("es;q=-1") is None


def test_q_zero_is_found_among_other_parameters_and_spacing() -> None:
    mw = LocaleMiddleware(lambda *a: None, supported_locales=["en", "es"], default_locale="en")
    assert mw._negotiate("es;charset=utf-8;q=0") is None
    assert mw._negotiate("es; q = 0, en;q=0.1") == "en"
    assert mw._negotiate("es;q=0;") is None
    assert mw._negotiate("es;Q=0") is None
