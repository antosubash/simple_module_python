"""Branding navigation follows the page guard rather than role names (#698)."""

import pytest
from branding.constants import MENU_URL, PERM_VIEW
from branding.module import BrandingModule
from simple_module_core.menu import MenuRegistry, MenuSection


@pytest.mark.parametrize("granted", [False, True])
@pytest.mark.parametrize("role", ["admin", "designer"])
def test_branding_menu_follows_view_permission(granted, role):
    registry = MenuRegistry()
    BrandingModule().register_menu_items(registry)
    items = registry.get_for_user(
        is_authenticated=True, roles=[role], permissions=[PERM_VIEW] if granted else []
    )[MenuSection.ADMIN_SIDEBAR]
    assert any(item["url"] == MENU_URL for item in items) is granted
