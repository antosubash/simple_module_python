"""Tests for PermissionRegistry: groups, roles, admin bypass."""

from __future__ import annotations

from simple_module_core.permissions import WILDCARD, PermissionRegistry


class TestPermissionRegistry:
    async def test_add_group(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.create"])
        assert "products.view" in reg.all_permissions
        assert "products.create" in reg.all_permissions

    async def test_add_single(self):
        reg = PermissionRegistry()
        reg.add("orders.view")
        assert reg.has("orders.view")

    async def test_auto_grouping(self):
        reg = PermissionRegistry()
        reg.add("orders.view")
        reg.add("orders.create")
        groups = reg.groups
        assert any(g.name == "orders" for g in groups)

    async def test_has(self):
        reg = PermissionRegistry()
        reg.add("test.perm")
        assert reg.has("test.perm") is True
        assert reg.has("nonexistent") is False

    async def test_admin_role_gets_all(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        perms = reg.get_permissions_for_roles(["admin"])
        assert "products.view" in perms
        assert "products.edit" in perms

    async def test_non_admin_gets_none_by_default(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view"])
        perms = reg.get_permissions_for_roles(["user"])
        assert len(perms) == 0

    async def test_custom_role_map(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        role_map = {"editor": ["products.edit"]}
        perms = reg.get_permissions_for_roles(["editor"], role_permission_map=role_map)
        assert "products.edit" in perms
        assert "products.view" not in perms

    async def test_extend_existing_group(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view"])
        reg.add_group("Products", ["products.delete"])
        perms = reg.all_permissions
        assert "products.view" in perms
        assert "products.delete" in perms


class TestPermissionRegistryAdvanced:
    async def test_no_duplicates(self):
        reg = PermissionRegistry()
        reg.add("products.view")
        reg.add("products.view")
        assert reg.all_permissions.count("products.view") == 1

    async def test_multiple_roles_union(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        role_map = {"viewer": ["products.view"], "editor": ["products.edit"]}
        perms = reg.get_permissions_for_roles(["viewer", "editor"], role_permission_map=role_map)
        assert "products.view" in perms
        assert "products.edit" in perms

    async def test_groups_list(self):
        reg = PermissionRegistry()
        reg.add_group("Auth", ["auth.login"])
        reg.add_group("Products", ["products.view"])
        assert len(reg.groups) == 2

    async def test_permissions_sorted(self):
        reg = PermissionRegistry()
        reg.add("z.last")
        reg.add("a.first")
        assert reg.all_permissions == ["a.first", "z.last"]


class TestPermissionRegistryMapRole:
    async def test_map_role_adds_entries(self):
        reg = PermissionRegistry()
        reg.map_role("user", ["users.self.profile"])
        assert "users.self.profile" in reg.role_map["user"]

    async def test_map_role_merges_into_existing_role(self):
        reg = PermissionRegistry()
        reg.map_role("user", ["users.self.profile"])
        reg.map_role("user", ["users.self.settings"])
        assert "users.self.profile" in reg.role_map["user"]
        assert "users.self.settings" in reg.role_map["user"]

    async def test_role_map_includes_default_admin_wildcard(self):
        reg = PermissionRegistry()
        assert WILDCARD in reg.role_map["admin"]

    async def test_role_map_returns_plain_dict_of_lists(self):
        reg = PermissionRegistry()
        reg.map_role("editor", ["products.edit"])
        result = reg.role_map
        assert isinstance(result, dict)
        for key, val in result.items():
            assert isinstance(key, str)
            assert isinstance(val, list)
