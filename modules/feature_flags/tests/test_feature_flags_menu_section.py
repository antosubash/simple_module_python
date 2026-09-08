"""Guards FeatureFlags's admin-sidebar menu placement (regression: GH #280 dropped it)."""

from __future__ import annotations

from feature_flags.constants import MENU_URL
from feature_flags.module import FeatureFlagsModule
from simple_module_core.menu import MenuRegistry, MenuSection


def test_feature_flags_menu_item_is_in_admin_sidebar() -> None:
    registry = MenuRegistry()
    FeatureFlagsModule().register_menu_items(registry)

    item = next(i for i in registry.all_items if i.url == MENU_URL)
    assert item.section == MenuSection.ADMIN_SIDEBAR


def test_permission_group_matches_the_menu_label() -> None:
    """The role editor lists this group beside the sidebar entry it governs;
    "Feature Flags" next to "Feature flags" reads as two different things."""
    from feature_flags.constants import MENU_LABEL, PERM_GROUP
    from simple_module_core.permissions import PermissionRegistry

    registry = PermissionRegistry()
    FeatureFlagsModule().register_permissions(registry)

    assert [g.name for g in registry.groups] == [PERM_GROUP]
    assert PERM_GROUP == MENU_LABEL
