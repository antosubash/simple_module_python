"""``/tenants/settings``: the active organisation's overridable settings (#382)."""

from __future__ import annotations

import pytest
from settings.contracts.registry import SettingDefinition

INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


@pytest.fixture(autouse=True)
def overridable(app):
    app.state.settings.registry.add(
        SettingDefinition(key="demo.motto", default="hi", tenant_overridable=True)
    )


async def test_owner_sees_the_overridable_keys(tenant_client):
    async with tenant_client() as me:
        await me.client.put("/api/settings/tenant/current/demo.motto", json={"value": "ours"})
        resp = await me.client.get("/tenants/settings", headers=INERTIA)
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["component"] == "Tenants/Settings"
    assert page["props"]["tenant"]["id"] == me.tenant_id
    row = next(r for r in page["props"]["settings"] if r["key"] == "demo.motto")
    assert (row["inherited"], row["value"], row["effective"]) == ("hi", "ours", "ours")


async def test_member_is_forbidden(tenant_client):
    async with tenant_client("member") as me:
        resp = await me.client.get("/tenants/settings", headers=INERTIA)
    assert resp.status_code == 403


async def test_sidebar_entry_follows_the_permission(tenant_client):
    async with tenant_client("admin") as admin, tenant_client("member") as member:
        admin_menu = (await admin.client.get("/tenants/", headers=INERTIA)).json()
        member_menu = (await member.client.get("/tenants/", headers=INERTIA)).json()

    def urls(page: dict) -> set[str]:
        return {item["url"] for item in page["props"]["menus"].get("sidebar", [])}

    assert "/tenants/settings" in urls(admin_menu)
    assert "/tenants/settings" not in urls(member_menu)
