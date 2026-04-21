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
        json={"reset_password_token_secret": "real-secret-value-48-chars-long-xxxxxxxxxx"},
    )
    original = app.state.users.settings.reset_password_token_secret
    resp = await authenticated_client.put(
        "/api/settings/modules/users",
        json={"reset_password_token_secret": "••••••••"},
    )
    assert resp.status_code == 200
    assert app.state.users.settings.reset_password_token_secret == original
