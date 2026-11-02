"""Files navigation follows the browse permission, including without tenants (#698)."""

import pytest
from file_storage.constants import ROUTE_PREFIX_VIEW, Permission
from file_storage.module import FileStorageModule
from simple_module_core.menu import MenuRegistry, MenuSection


@pytest.mark.parametrize("granted", [False, True])
def test_file_storage_menu_follows_download_permission(granted):
    registry = MenuRegistry()
    FileStorageModule().register_menu_items(registry)
    items = registry.get_for_user(
        is_authenticated=True,
        roles=["user"],
        permissions=[Permission.DOWNLOAD] if granted else [],
    )[MenuSection.SIDEBAR]
    assert any(item["url"] == f"{ROUTE_PREFIX_VIEW}/" for item in items) is granted
