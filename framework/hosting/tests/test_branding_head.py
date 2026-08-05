"""Tests for the root-template branding head metadata helper."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_hosting._inertia_setup import branding_head


def _request(branding: object | None) -> SimpleNamespace:
    state = SimpleNamespace()
    if branding is not None:
        state.branding = branding
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_defaults_when_branding_not_installed() -> None:
    meta = branding_head(_request(None))
    assert meta == {"app_name": "SimpleModule", "theme_color": None, "favicon_url": None}


def test_reads_app_name_and_theme_color() -> None:
    settings = SimpleNamespace(app_name="Acme", primary_color="#1a7dd1")
    meta = branding_head(_request(SimpleNamespace(settings=settings)))
    assert meta["app_name"] == "Acme"
    assert meta["theme_color"] == "#1a7dd1"


def test_blank_values_fall_back() -> None:
    settings = SimpleNamespace(app_name="", primary_color="")
    meta = branding_head(_request(SimpleNamespace(settings=settings)))
    assert meta == {"app_name": "SimpleModule", "theme_color": None, "favicon_url": None}


def test_favicon_url_comes_from_the_module_not_from_here() -> None:
    # The framework must not know branding's route shape (SM009), so it reads
    # whatever the module exposes rather than assembling a URL itself.
    services = SimpleNamespace(
        settings=SimpleNamespace(app_name="Acme", primary_color=""),
        favicon_url="/api/branding/favicon?v=abc",
    )
    assert branding_head(_request(services))["favicon_url"] == "/api/branding/favicon?v=abc"


def test_favicon_url_is_none_on_a_host_without_that_attribute() -> None:
    # An older branding release exposes no favicon_url; the shell just omits
    # the link rather than erroring, and BrandingHead still sets it client-side.
    services = SimpleNamespace(settings=SimpleNamespace(app_name="Acme", primary_color=""))
    assert branding_head(_request(services))["favicon_url"] is None
