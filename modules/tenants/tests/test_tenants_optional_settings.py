"""Organisation settings are available only with the optional Settings module."""

import pytest
from simple_module_hosting.settings import Settings


@pytest.fixture(params=[False, True], ids=["without-settings", "with-settings"])
def settings(settings: Settings, request: pytest.FixtureRequest) -> Settings:
    modules = ["Auth", "Users", "Tenants"]
    if request.param:
        modules.append("Settings")
    return settings.model_copy(update={"modules_enabled": modules})


async def test_settings_route_and_menu_follow_module_availability(app, tenant_client):
    enabled = getattr(app.state, "settings", None) is not None
    registered_urls = {item.url for item in app.state.sm.menu_registry.all_items}
    assert ("/tenants/settings" in registered_urls) is enabled
    async with tenant_client() as me:
        page = await me.client.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.status_code == 200, page.text
        urls = {item["url"] for item in page.json()["props"]["menus"]["sidebar"]}
        assert "/tenants/members" in urls
        assert ("/tenants/settings" in urls) is enabled

        response = await me.client.get("/tenants/settings", headers={"X-Inertia": "true"})
        assert response.status_code == (200 if enabled else 404), response.text
        if enabled:
            assert response.json()["component"] == "Tenants/Settings"
            assert response.json()["props"]["tenant"]["id"] == me.tenant_id
