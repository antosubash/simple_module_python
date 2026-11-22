"""Shared account-link and authentication policy (#971, #975)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_hosting.auth_policy import login_redirect_url
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.public_urls import public_origin


def test_public_origin_prefers_module_then_host():
    host = HostSettings(public_base_url="https://host.example/")
    assert public_origin(host, "https://module.example/") == "https://module.example"
    assert public_origin(host) == "https://host.example"
    assert public_origin(HostSettings()) == ""


@pytest.mark.parametrize("provider", ["Users", "Keycloak", "Oidc"])
def test_login_destination_uses_host_and_falls_back_without_dashboard(provider):
    app = FastAPI()
    app.state.host = SimpleNamespace(settings=HostSettings())
    app.state.sm = SimpleNamespace(
        modules=(), view_prefixes={provider: "/auth", "Home": "", "Other": "/o"}
    )
    assert login_redirect_url(app, provider) == "/"
    app.state.sm.view_prefixes = {provider: "/auth", "Other": "/o"}
    assert login_redirect_url(app, provider) == "/o/"
    app.state.host.settings = HostSettings(login_redirect_url="/custom/")
    assert login_redirect_url(app, provider) == "/custom/"


@pytest.mark.parametrize("value", ["", "   "])
def test_host_normalizes_blank_login_destination(value):
    assert HostSettings(login_redirect_url=value).login_redirect_url == "/dashboard/"


def test_host_preserves_valid_login_destination():
    assert HostSettings(login_redirect_url="/home/").login_redirect_url == "/home/"


@pytest.mark.parametrize(
    "package,removed",
    [
        (
            "users",
            [
                "cookie_secure",
                "login_redirect_url",
                "bootstrap_email",
                "bootstrap_password",
                "bootstrap_user_email",
                "bootstrap_user_password",
            ],
        ),
        ("keycloak", ["admin_role", "login_redirect_url"]),
        ("oidc", ["login_redirect_url"]),
        ("background_tasks", ["max_retries"]),
    ],
)
def test_removed_rows_are_ignored_before_parsing(package, removed, caplog):
    from background_tasks.core.settings import BackgroundTasksSettings
    from keycloak.core.settings import KeycloakSettings
    from oidc.core.settings import OidcSettings
    from simple_module_core.settings.settings_hydrate import build_settings
    from users.core.settings import UsersSettings

    cls = {
        "users": UsersSettings,
        "keycloak": KeycloakSettings,
        "oidc": OidcSettings,
        "background_tasks": BackgroundTasksSettings,
    }[package]
    cfg = build_settings(cls, dict.fromkeys(removed, ("invalid legacy value", "int")))
    assert all(not hasattr(cfg, name) for name in removed)
    assert not caplog.records
