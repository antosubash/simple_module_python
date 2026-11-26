"""URL validation follows the regular settings save error contract."""

import pytest


@pytest.mark.parametrize(
    ("package", "field", "value", "hint"),
    [
        ("tenants", "subdomain_base", "https://example.com", "hostname"),
        ("users", "base_url", "javascript:alert(1)", "http(s)"),
        ("tenants", "public_base_url", "javascript:alert(1)", "http(s)"),
        ("tenants", "public_base_url", "https://user:password@example.com", "credentials"),
        ("tenants", "public_base_url", "https://example.com/app?next=/other", "query"),
        ("tenants", "public_base_url", "https://example.com/app#section", "fragment"),
    ],
)
async def test_invalid_url_save_returns_field_error_without_writing(
    authenticated_client, app, package, field, value, hint
):
    from settings.core.service import SettingService
    from settings.module_settings.store import SettingsStore

    original = getattr(app.state, package).settings
    response = await authenticated_client.put(
        f"/api/settings/modules/{package}", json={field: value}
    )
    assert response.status_code == 422, response.text
    error = response.json()["detail"][0]
    assert error["loc"][-1] == field
    assert hint in error["msg"]
    assert getattr(app.state, package).settings is original
    async with app.state.sm.db.session_factory() as db:
        assert await SettingsStore(SettingService(db)).get_overrides(package) == {}


@pytest.mark.parametrize(
    ("package", "field", "value", "expected"),
    [
        ("tenants", "subdomain_base", "  ExAmPlE.COM  ", "example.com"),
        ("users", "base_url", "  https://example.com  ", "https://example.com"),
        (
            "tenants",
            "public_base_url",
            "  https://example.com/app/  ",
            "https://example.com/app/",
        ),
    ],
)
async def test_url_save_persists_normalized_value(
    authenticated_client, app, package, field, value, expected
):
    from settings.core.service import SettingService
    from settings.module_settings.store import SettingsStore

    response = await authenticated_client.put(
        f"/api/settings/modules/{package}", json={field: value}
    )
    assert response.status_code == 200, response.text
    assert getattr(getattr(app.state, package).settings, field) == expected
    async with app.state.sm.db.session_factory() as db:
        stored = await SettingsStore(SettingService(db)).get_overrides(package)
    assert stored[field] == (expected, "string")
