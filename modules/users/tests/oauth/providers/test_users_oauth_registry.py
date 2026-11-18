"""Registered factories drive both login dispatch and translated buttons (#964)."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx_oauth.clients.github import GitHubOAuth2
from settings.contracts.events import SettingsReloaded
from simple_module_core.events import EventBus
from simple_module_test import inertia_page
from starlette.requests import Request
from users.core.settings import UsersSettings
from users.oauth import OAuthProvider


def _factory(app):
    settings = app.state.custom.settings
    if not settings.enabled or not settings.client_id or not settings.client_secret:
        return None
    return OAuthProvider(
        "custom", "Custom SSO", GitHubOAuth2(settings.client_id, settings.client_secret)
    )


def _configure(app):
    app.state.custom = SimpleNamespace(
        settings=SimpleNamespace(enabled=True, client_id="custom-id", client_secret="custom-secret")
    )


def _failing_factory(app):
    if not app.state.custom.settings.enabled:
        raise RuntimeError("Custom provider unavailable")
    return _factory(app)


def test_factory_failure_publishes_fresh_clients_and_buttons(caplog):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    app = FastAPI()
    app.state.users = SimpleNamespace(
        settings=UsersSettings(oauth_google_client_id="g-id", oauth_google_client_secret="g-secret")
    )
    _configure(app)
    register_oauth_provider(app, "custom", _failing_factory)
    register_oauth_provider(
        app,
        "healthy",
        lambda app: OAuthProvider("healthy", "Healthy SSO", GitHubOAuth2("id", "secret")),
    )
    _build_oauth_clients(app)
    assert set(app.state.users.oauth_clients) == {"google", "custom", "healthy"}

    app.state.users.settings = UsersSettings(
        oauth_github_client_id="gh-id", oauth_github_client_secret="gh-secret"
    )
    app.state.custom.settings.enabled = False
    _build_oauth_clients(app)

    assert set(app.state.users.oauth_clients) == {"github", "healthy"}
    assert app.state.users.oauth_providers == [
        {"name": "github", "display_name": "GitHub"},
        {"name": "healthy", "display_name": "Healthy SSO"},
    ]
    assert any(
        record.levelname == "ERROR" and "custom" in record.message for record in caplog.records
    )


@pytest.mark.anyio
async def test_reload_removes_google_callbacks_even_when_custom_factory_fails(
    users_app, anon_client
):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    _configure(users_app)
    register_oauth_provider(users_app, "custom", _failing_factory)
    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_google_client_id": "g-id", "oauth_google_client_secret": "g-secret"}
    )
    _build_oauth_clients(users_app)
    assert set(users_app.state.users.oauth_clients) == {"google", "custom"}

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_google_client_id": "", "oauth_google_client_secret": ""}
    )
    users_app.state.custom.settings.enabled = False
    await users_app.state.sm.event_bus.publish(SettingsReloaded(package="users", changed=()))

    assert users_app.state.users.oauth_clients == {}
    assert users_app.state.users.oauth_providers == []
    for name in ("google", "custom"):
        response = await anon_client.get(f"/api/users/auth/{name}/callback")
        assert response.status_code == 404
        assert response.json()["detail"] == "OAUTH_PROVIDER_NOT_FOUND"


def test_registry_builds_custom_provider_at_startup_and_is_app_scoped():
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings())
    _configure(app)
    register_oauth_provider(app, "custom", _factory, label_key="custom.login.sso", icon="key")
    _build_oauth_clients(app)

    assert app.state.users.oauth_clients["custom"].client.client_id == "custom-id"
    assert app.state.users.oauth_providers == [
        {
            "name": "custom",
            "display_name": "Custom SSO",
            "label_key": "custom.login.sso",
            "icon": "key",
        }
    ]
    other = FastAPI()
    other.state.users = SimpleNamespace(settings=UsersSettings())
    _build_oauth_clients(other)
    assert other.state.users.oauth_clients == {}
    assert other.state.users.oauth_providers == []


@pytest.mark.parametrize("name", ["custom", "google", "github", "microsoft", "oidc"])
def test_duplicate_registration_is_refused(name):
    from users.contracts import register_oauth_provider

    app = FastAPI()
    if name == "custom":
        register_oauth_provider(app, name, _factory)
    with pytest.raises(ValueError, match="already registered"):
        register_oauth_provider(app, name, _factory)


@pytest.mark.parametrize("name", ["", "../custom", "custom/name", "custom?next=x", "Custom"])
def test_provider_name_must_be_a_safe_url_segment(name):
    from users.contracts import register_oauth_provider

    with pytest.raises(ValueError, match="name"):
        register_oauth_provider(FastAPI(), name, _factory)


def test_factory_cannot_change_registered_provider_name():
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings())
    _configure(app)
    register_oauth_provider(app, "another", _factory)
    with pytest.raises(ValueError, match="name"):
        _build_oauth_clients(app)


@pytest.mark.anyio
async def test_reload_rebuilds_custom_factory_from_live_settings_without_db():
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients
    from users.module import UsersModule
    from users.web.shared_props import users_shared_props

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings())
    _configure(app)
    register_oauth_provider(app, "custom", _factory, label_key="custom.login.sso", icon="key")
    _build_oauth_clients(app)
    original = app.state.users.oauth_clients["custom"]
    bus = EventBus()
    UsersModule().register_event_handlers(bus, app)
    app.state.custom.settings.client_id = "reloaded-id"
    app.state.users.settings = UsersSettings(
        oauth_github_client_id="g-id", oauth_github_client_secret="g-secret"
    )
    await bus.publish(SettingsReloaded(package="users", changed=()))

    clients = app.state.users.oauth_clients
    assert set(clients) == {"github", "custom"}
    assert clients["custom"] is not original
    assert clients["custom"].client.client_id == "reloaded-id"
    request = Request({"type": "http", "app": app})
    assert users_shared_props(request)["oauth_providers"] == [
        {"name": "github", "display_name": "GitHub"},
        {
            "name": "custom",
            "display_name": "Custom SSO",
            "label_key": "custom.login.sso",
            "icon": "key",
        },
    ]

    app.state.custom.settings.enabled = False
    await bus.publish(SettingsReloaded(package="users", changed=()))
    assert set(app.state.users.oauth_clients) == {"github"}
    assert users_shared_props(request)["oauth_providers"] == [
        {"name": "github", "display_name": "GitHub"}
    ]


@pytest.mark.parametrize("update", [{"enabled": False}, {"client_id": ""}, {"client_secret": ""}])
def test_disabled_or_incomplete_factory_has_no_client_or_button(update):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings())
    _configure(app)
    register_oauth_provider(app, "custom", _factory)
    for field, value in update.items():
        setattr(app.state.custom.settings, field, value)
    _build_oauth_clients(app)
    assert app.state.users.oauth_clients == {}
    assert app.state.users.oauth_providers == []


@pytest.mark.anyio
async def test_custom_provider_survives_reload_and_appears_on_login(users_app, anon_client):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    _configure(users_app)
    register_oauth_provider(users_app, "custom", _factory, label_key="custom.login.sso", icon="key")
    _build_oauth_clients(users_app)
    old_client = users_app.state.users.oauth_clients["custom"].client
    users_app.state.custom.settings.client_id = "updated-id"
    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_google_client_id": "g-id", "oauth_google_client_secret": "g-secret"}
    )
    await users_app.state.sm.event_bus.publish(SettingsReloaded(package="users", changed=()))

    clients = users_app.state.users.oauth_clients
    assert set(clients) == {"google", "custom"}
    assert clients["custom"].client is not old_client
    assert clients["custom"].client.client_id == "updated-id"
    response = await anon_client.get("/users/login")
    buttons = inertia_page(response).props["oauth_providers"]
    assert buttons == [
        {"name": "google", "display_name": "Google"},
        {
            "name": "custom",
            "display_name": "Custom SSO",
            "label_key": "custom.login.sso",
            "icon": "key",
        },
    ]
    response = await anon_client.get("/api/users/auth/custom/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["client_id"] == ["updated-id"]
    assert query["redirect_uri"] == ["http://testserver/api/users/auth/custom/callback"]
    assert query["state"][0]


@pytest.mark.anyio
@pytest.mark.parametrize("update", [{"enabled": False}, {"client_id": ""}, {"client_secret": ""}])
async def test_disabled_or_incomplete_provider_removed_on_reload(users_app, anon_client, update):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    _configure(users_app)
    register_oauth_provider(users_app, "custom", _factory)
    _build_oauth_clients(users_app)
    assert "custom" in users_app.state.users.oauth_clients
    for field, value in update.items():
        setattr(users_app.state.custom.settings, field, value)
    await users_app.state.sm.event_bus.publish(SettingsReloaded(package="users", changed=()))

    assert users_app.state.users.oauth_clients == {}
    assert users_app.state.users.oauth_providers == []
    response = await anon_client.get("/users/login")
    assert inertia_page(response).props["oauth_providers"] == []
    assert (await anon_client.get("/api/users/auth/custom/login")).status_code == 404
