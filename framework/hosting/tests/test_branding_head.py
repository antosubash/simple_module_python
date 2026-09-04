"""Tests for the root-template branding head metadata helper."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_hosting._favicon import default_favicon_data_uri
from simple_module_hosting._inertia_setup import branding_head


def _request(branding: object | None) -> SimpleNamespace:
    state = SimpleNamespace()
    if branding is not None:
        state.branding = branding
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_defaults_when_branding_not_installed() -> None:
    meta = branding_head(_request(None))
    assert meta == {
        "app_name": "SimpleModule",
        "theme_color": None,
        "favicon_url": default_favicon_data_uri("SimpleModule"),
    }


def test_reads_app_name_and_theme_color() -> None:
    settings = SimpleNamespace(app_name="Acme", primary_color="#1a7dd1")
    meta = branding_head(_request(SimpleNamespace(settings=settings)))
    assert meta["app_name"] == "Acme"
    assert meta["theme_color"] == "#1a7dd1"


def test_blank_values_fall_back() -> None:
    settings = SimpleNamespace(app_name="", primary_color="")
    meta = branding_head(_request(SimpleNamespace(settings=settings)))
    assert meta == {
        "app_name": "SimpleModule",
        "theme_color": None,
        "favicon_url": default_favicon_data_uri("SimpleModule"),
    }


def test_favicon_url_comes_from_the_module_not_from_here() -> None:
    # The framework must not know branding's route shape (SM009), so it reads
    # whatever the module exposes rather than assembling a URL itself.
    services = SimpleNamespace(
        settings=SimpleNamespace(app_name="Acme", primary_color=""),
        favicon_url="/api/branding/favicon?v=abc",
    )
    assert branding_head(_request(services))["favicon_url"] == "/api/branding/favicon?v=abc"


def test_an_uploaded_favicon_always_wins_over_the_default() -> None:
    services = SimpleNamespace(
        settings=SimpleNamespace(app_name="Acme", primary_color="#1a7dd1"),
        favicon_url="/api/branding/favicon?v=abc",
    )
    assert branding_head(_request(services))["favicon_url"] == "/api/branding/favicon?v=abc"


def test_a_host_without_that_attribute_still_gets_a_favicon() -> None:
    # An older branding release exposes no favicon_url. Omitting the link tag
    # sends the browser to /favicon.ico, which this app does not route — a 404
    # (or a 302 to the login page) in the console on every full page load — so
    # the generated mark stands in.
    services = SimpleNamespace(settings=SimpleNamespace(app_name="Acme", primary_color=""))
    assert branding_head(_request(services))["favicon_url"] == default_favicon_data_uri("Acme")


def test_the_default_follows_the_configured_brand_colour() -> None:
    services = SimpleNamespace(settings=SimpleNamespace(app_name="Acme", primary_color="#1a7dd1"))
    favicon = branding_head(_request(services))["favicon_url"]
    assert favicon == default_favicon_data_uri("Acme", "#1a7dd1")
    assert favicon != default_favicon_data_uri("Acme")
