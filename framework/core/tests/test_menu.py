"""Tests for MenuRegistry: adding items, sorting, filtering, sections."""

from __future__ import annotations

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection


class TestMenuRegistry:
    async def test_add_and_all_items(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Dashboard", url="/dashboard", order=1))
        reg.add(MenuItem(label="Products", url="/products", order=2))
        assert len(reg.all_items) == 2
        assert reg.all_items[0].label == "Dashboard"

    async def test_add_many(self):
        reg = MenuRegistry()
        reg.add_many(
            [
                MenuItem(label="A", url="/a", order=1),
                MenuItem(label="B", url="/b", order=2),
            ]
        )
        assert len(reg.all_items) == 2

    async def test_sorted_by_order(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Z", url="/z", order=99))
        reg.add(MenuItem(label="A", url="/a", order=1))
        assert reg.all_items[0].label == "A"
        assert reg.all_items[1].label == "Z"

    async def test_filter_unauthenticated(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Public", url="/pub", requires_auth=False))
        reg.add(MenuItem(label="Private", url="/priv", requires_auth=True))

        result = reg.get_for_user(is_authenticated=False)
        sidebar = result["sidebar"]
        assert len(sidebar) == 1
        assert sidebar[0]["label"] == "Public"

    async def test_filter_authenticated_sees_all(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Public", url="/pub", requires_auth=False))
        reg.add(MenuItem(label="Private", url="/priv", requires_auth=True))

        result = reg.get_for_user(is_authenticated=True)
        sidebar = result["sidebar"]
        assert len(sidebar) == 2

    async def test_filter_by_roles(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Admin Panel", url="/admin", roles=["admin"]))
        reg.add(MenuItem(label="Dashboard", url="/dash"))

        result = reg.get_for_user(is_authenticated=True, roles=["user"])
        sidebar = result["sidebar"]
        labels = [i["label"] for i in sidebar]
        assert "Dashboard" in labels
        assert "Admin Panel" not in labels

        result = reg.get_for_user(is_authenticated=True, roles=["admin"])
        sidebar = result["sidebar"]
        labels = [i["label"] for i in sidebar]
        assert "Admin Panel" in labels

    async def test_sections(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Side", url="/s", section=MenuSection.SIDEBAR))
        reg.add(MenuItem(label="Nav", url="/n", section=MenuSection.NAVBAR))
        reg.add(MenuItem(label="Drop", url="/d", section=MenuSection.USER_DROPDOWN))

        result = reg.get_for_user(is_authenticated=True)
        assert len(result["sidebar"]) == 1
        assert len(result["navbar"]) == 1
        assert len(result["userDropdown"]) == 1


class TestMenuRegistryAdvanced:
    async def test_multiple_roles_any_match(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Editor", url="/edit", roles=["editor", "admin"]))
        result = reg.get_for_user(is_authenticated=True, roles=["editor"])
        assert len(result["sidebar"]) == 1

    async def test_empty_registry(self):
        reg = MenuRegistry()
        result = reg.get_for_user(is_authenticated=True)
        assert all(len(v) == 0 for v in result.values())

    async def test_admin_sidebar_section(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Users", url="/admin/users", section=MenuSection.ADMIN_SIDEBAR))
        result = reg.get_for_user(is_authenticated=True)
        assert len(result["adminSidebar"]) == 1

    async def test_icon_preserved(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Home", url="/", icon="home"))
        result = reg.get_for_user(is_authenticated=True)
        assert result["sidebar"][0]["icon"] == "home"

    async def test_group_default_empty(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Home", url="/"))
        result = reg.get_for_user(is_authenticated=True)
        assert result["sidebar"][0]["group"] == ""

    async def test_group_serialized(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Users", url="/users", group="Administration"))
        reg.add(MenuItem(label="Settings", url="/settings", group="System"))
        result = reg.get_for_user(is_authenticated=True)
        groups = [i["group"] for i in result["sidebar"]]
        assert groups == ["Administration", "System"]


class TestPermissionFiltering:
    """An entry that 403s on click is worse than no entry at all.

    Roles alone could not express this: hard-coding ``roles=["admin"]`` hides
    the screen from a custom role that legitimately holds the permission, while
    still showing it to admin-adjacent roles that cannot open it.
    """

    async def test_entry_hidden_without_the_permission(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Settings", url="/settings/", permissions=["settings.view"]))
        result = reg.get_for_user(is_authenticated=True, permissions=["users.manage"])
        assert result["sidebar"] == []

    async def test_entry_shown_with_the_permission(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Settings", url="/settings/", permissions=["settings.view"]))
        result = reg.get_for_user(is_authenticated=True, permissions=["settings.view"])
        assert [i["label"] for i in result["sidebar"]] == ["Settings"]

    async def test_permission_granted_by_a_custom_role_is_enough(self):
        """No role check involved — holding the key is what matters."""
        reg = MenuRegistry()
        reg.add(MenuItem(label="Settings", url="/settings/", permissions=["settings.view"]))
        result = reg.get_for_user(
            is_authenticated=True, roles=["auditor"], permissions=["settings.view"]
        )
        assert len(result["sidebar"]) == 1

    async def test_all_declared_permissions_are_required(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="X", url="/x", permissions=["a.view", "a.manage"]))
        assert reg.get_for_user(is_authenticated=True, permissions=["a.view"])["sidebar"] == []
        both = reg.get_for_user(is_authenticated=True, permissions=["a.view", "a.manage"])
        assert len(both["sidebar"]) == 1

    async def test_no_declared_permissions_means_no_check(self):
        """Existing entries must keep working without opting in."""
        reg = MenuRegistry()
        reg.add(MenuItem(label="Home", url="/"))
        assert len(reg.get_for_user(is_authenticated=True, permissions=[])["sidebar"]) == 1

    async def test_omitting_permissions_entirely_hides_gated_entries(self):
        """A caller that passes no permissions holds none — fail closed."""
        reg = MenuRegistry()
        reg.add(MenuItem(label="Settings", url="/settings/", permissions=["settings.view"]))
        assert reg.get_for_user(is_authenticated=True)["sidebar"] == []


_CATALOG = {
    "users.nav.users": "Usuarios",
    "ui.nav_groups.administration": "Administración",
}


class TestMenuLabelTranslation:
    """Label/group keys resolve server-side so every render site stays dumb."""

    def _translate(self, key: str) -> str:
        # Mirrors Translator.t(), which echoes the key back when it is missing.
        return _CATALOG.get(key, key)

    async def test_keys_are_translated(self):
        reg = MenuRegistry()
        reg.add(
            MenuItem(
                label="Users",
                url="/users/admin",
                label_key="users.nav.users",
                group="Administration",
                group_key="ui.nav_groups.administration",
            )
        )
        item = reg.get_for_user(is_authenticated=True, translate=self._translate)["sidebar"][0]
        assert item["label"] == "Usuarios"
        assert item["group"] == "Administración"

    async def test_missing_key_falls_back_to_the_literal_label(self):
        """An unresolved key must not put a raw dotted key on screen."""
        reg = MenuRegistry()
        reg.add(
            MenuItem(
                label="Reports",
                url="/reports",
                label_key="reports.nav.absent",
                group="Ops",
                group_key="ui.nav_groups.absent",
            )
        )
        item = reg.get_for_user(is_authenticated=True, translate=self._translate)["sidebar"][0]
        assert item["label"] == "Reports"
        assert item["group"] == "Ops"

    async def test_items_without_keys_ship_their_literal_label(self):
        """Third-party modules predating label_key keep working unchanged."""
        reg = MenuRegistry()
        reg.add(MenuItem(label="Legacy", url="/legacy", group="Tools"))
        item = reg.get_for_user(is_authenticated=True, translate=self._translate)["sidebar"][0]
        assert item["label"] == "Legacy"
        assert item["group"] == "Tools"

    async def test_no_translator_ships_literal_labels(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Users", url="/users/admin", label_key="users.nav.users"))
        item = reg.get_for_user(is_authenticated=True)["sidebar"][0]
        assert item["label"] == "Users"
