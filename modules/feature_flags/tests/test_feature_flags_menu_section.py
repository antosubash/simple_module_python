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
