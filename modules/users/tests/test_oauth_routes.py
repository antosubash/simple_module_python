"""OAuth HTTP dispatcher + live-reload tests.

Exercises the running app: the provider-agnostic ``/auth/{provider}/{login,callback}``
dispatcher (resolution, 404, state CSRF) and the ``SettingsReloaded`` hot-reload of the
provider cache. Provider construction and the account model are unit-tested in
``test_oauth.py``.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Provider-agnostic dispatcher (request-time client resolution)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_oauth_login_redirects_for_configured_provider(users_app, anon_client):
    from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
    from users.oauth import OAuthProvider

    users_app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", MicrosoftGraphOAuth2("ms-id", "ms-secret")
    )
    resp = await anon_client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "login.microsoftonline.com" in resp.headers["location"]


@pytest.mark.anyio
async def test_oauth_login_404_for_unknown_provider(anon_client):
    resp = await anon_client.get("/api/users/auth/nope/login", follow_redirects=False)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_oauth_callback_rejects_bad_state(users_app, anon_client):
    from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
    from users.oauth import OAuthProvider

    users_app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", MicrosoftGraphOAuth2("ms-id", "ms-secret")
    )
    resp = await anon_client.get(
        "/api/users/auth/microsoft/callback?code=abc&state=bad", follow_redirects=False
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Live cache rebuild on SettingsReloaded
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_settings_reload_adds_provider_to_cache(users_app):
    from settings.contracts.events import SettingsReloaded

    assert users_app.state.users.oauth_clients == {}
    assert users_app.state.users.oauth_providers == []

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "ms-id", "oauth_microsoft_client_secret": "ms-secret"}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )

    assert "microsoft" in users_app.state.users.oauth_clients
    buttons = users_app.state.users.oauth_providers
    assert {"name": "microsoft", "display_name": "Microsoft"} in buttons


@pytest.mark.anyio
async def test_settings_reload_removes_cleared_provider(users_app):
    from settings.contracts.events import SettingsReloaded

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "ms-id", "oauth_microsoft_client_secret": "ms-secret"}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )
    assert "microsoft" in users_app.state.users.oauth_clients

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "", "oauth_microsoft_client_secret": ""}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )
    assert "microsoft" not in users_app.state.users.oauth_clients


@pytest.mark.anyio
async def test_settings_reload_ignores_other_packages(users_app):
    from settings.contracts.events import SettingsReloaded

    sentinel = object()
    users_app.state.users.oauth_clients["microsoft"] = sentinel
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="background_tasks", changed=("broker_url",))
    )
    assert users_app.state.users.oauth_clients["microsoft"] is sentinel
