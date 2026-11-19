from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_modules_returns_registered_packages(authenticated_client):
    resp = await authenticated_client.get("/api/settings/modules")
    assert resp.status_code == 200
    payload = resp.json()
    packages = {m["package"] for m in payload["modules"]}
    assert {"settings", "host"} <= packages


@pytest.mark.asyncio
async def test_put_module_setting_persists_and_hot_reloads(authenticated_client, app):
    resp = await authenticated_client.put(
        "/api/settings/modules/host",
        json={"multi_tenant": True},
    )
    assert resp.status_code == 200, resp.text
    assert app.state.host.settings.multi_tenant is True


@pytest.mark.asyncio
async def test_put_validation_error_surfaces_422(authenticated_client, app):
    resp = await authenticated_client.put(
        "/api/settings/modules/host",
        json={"i18n_default_locale": "de"},
    )
    assert resp.status_code == 422
    assert "i18n_default_locale" in resp.text


async def test_put_choice_uses_normalized_field_value(authenticated_client, app):
    response = await authenticated_client.put(
        "/api/settings/modules/users", json={"cookie_samesite": "Strict"}
    )

    assert response.status_code == 200, response.text
    assert app.state.users.settings.cookie_samesite == "strict"
    response = await authenticated_client.get("/api/settings/modules")
    assert response.status_code == 200
    users = next(m for m in response.json()["modules"] if m["package"] == "users")
    field = next(f for f in users["fields"] if f["name"] == "cookie_samesite")
    assert field["value"] == "strict"


@pytest.mark.asyncio
async def test_put_rejects_and_does_not_persist_unbounded_background_task_values(
    authenticated_client, app
):
    from settings.core.service import SettingService
    from settings.module_settings.store import SettingsStore

    original = app.state.background_tasks.settings
    resp = await authenticated_client.put(
        "/api/settings/modules/background_tasks",
        json={"retention_days": -5, "outbox_lease_seconds": -1},
    )

    assert resp.status_code == 422
    assert {error["loc"][-1] for error in resp.json()["detail"]} == {
        "retention_days",
        "outbox_lease_seconds",
    }
    assert app.state.background_tasks.settings is original
    # The app's own DB: ``db_session`` is a separate engine and reads ``{}``
    # whether or not the bad values were written.
    async with app.state.sm.db.session_factory() as db:
        assert await SettingsStore(SettingService(db)).get_overrides("background_tasks") == {}


@pytest.mark.asyncio
async def test_delete_field_resets_to_default(authenticated_client, app):
    await authenticated_client.put("/api/settings/modules/host", json={"multi_tenant": True})
    assert app.state.host.settings.multi_tenant is True
    resp = await authenticated_client.delete("/api/settings/modules/host/multi_tenant")
    assert resp.status_code == 204
    assert app.state.host.settings.multi_tenant is False


@pytest.mark.asyncio
async def test_put_secret_mask_sentinel_is_noop(authenticated_client, app):
    await authenticated_client.put(
        "/api/settings/modules/users",
        json={"oauth_google_client_secret": "real-secret-value-48-chars-long-xxxxxxxxxx"},
    )
    original = app.state.users.settings.oauth_google_client_secret
    resp = await authenticated_client.put(
        "/api/settings/modules/users",
        json={"oauth_google_client_secret": "••••••••"},
    )
    assert resp.status_code == 200
    assert app.state.users.settings.oauth_google_client_secret == original


async def test_host_body_guard_save_and_clear_apply_without_restart(authenticated_client, app):
    response = await authenticated_client.put(
        "/api/settings/modules/host", json={"max_request_body_bytes": 32}
    )
    assert response.status_code == 200
    response = await authenticated_client.post("/api/guard-probe", content=b"x" * 33)
    assert response.status_code == 413
    assert app.state.host.request_guards.max_bytes == 32
    response = await authenticated_client.delete(
        "/api/settings/modules/host/max_request_body_bytes"
    )
    assert response.status_code == 204
    response = await authenticated_client.post("/api/guard-probe", content=b"x" * 33)
    assert response.status_code != 413
    assert app.state.host.request_guards.max_bytes == 10 * 1024 * 1024


async def test_invalid_guard_save_keeps_the_previous_snapshot(authenticated_client, app):
    previous = app.state.host.request_guards
    response = await authenticated_client.put(
        "/api/settings/modules/host",
        json={"cors_allow_origins": ["*"], "cors_allow_credentials": True},
    )
    assert response.status_code == 422
    assert app.state.host.request_guards is previous
