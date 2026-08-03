"""Micro-benchmarks for the Inertia shared-props hot path.

``InertiaLayoutDataMiddleware`` runs on every HTTP request. These cover the
pure-function parts of that path — menu filtering and wildcard permission
expansion — so a middleware change gets a sub-second regression signal without
standing up a full load test.

Sized to a realistically loaded app: 40 menu items and 160 permissions across
20 groups. Run with ``make bench``.
"""

from __future__ import annotations

import pytest
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.permissions import expand_permissions, resolve_permissions

pytestmark = pytest.mark.perf

N_MENU_ITEMS = 40
N_PERMISSION_GROUPS = 20
N_PERMS_PER_GROUP = 8
ADMIN_ROLES = ["admin"]
EDITOR_ROLES = ["editor"]


@pytest.fixture
def menu_registry() -> MenuRegistry:
    """A registry with a realistic number of items, half of them role-gated."""
    registry = MenuRegistry()
    registry.add_many(
        [
            MenuItem(
                label=f"Item {i}",
                url=f"/module-{i}/",
                icon="box",
                order=i,
                section=MenuSection.SIDEBAR,
                roles=["admin"] if i % 2 else [],
            )
            for i in range(N_MENU_ITEMS)
        ]
    )
    return registry


@pytest.fixture
def permission_registry() -> PermissionRegistry:
    registry = PermissionRegistry()
    for g in range(N_PERMISSION_GROUPS):
        registry.add_group(f"Group{g}", [f"group{g}.perm{p}" for p in range(N_PERMS_PER_GROUP)])
    return registry


def test_menu_get_for_user_admin(benchmark, menu_registry: MenuRegistry) -> None:
    """Per-request menu filtering + dict construction for an admin."""
    result = benchmark(lambda: menu_registry.get_for_user(is_authenticated=True, roles=ADMIN_ROLES))
    assert result[MenuSection.SIDEBAR.value]


def test_menu_get_for_user_non_admin(benchmark, menu_registry: MenuRegistry) -> None:
    """Same path for a principal that fails half the role checks."""
    result = benchmark(
        lambda: menu_registry.get_for_user(is_authenticated=True, roles=EDITOR_ROLES)
    )
    assert result[MenuSection.SIDEBAR.value]


def test_permissions_expand_wildcard(benchmark, permission_registry: PermissionRegistry) -> None:
    """Wildcard expansion for an admin — sorts the full permission list."""
    resolved = resolve_permissions(ADMIN_ROLES, role_map=permission_registry.role_map)
    all_perms = permission_registry.all_permissions
    result = benchmark(lambda: expand_permissions(resolved, all_perms))
    assert len(result) == N_PERMISSION_GROUPS * N_PERMS_PER_GROUP


def test_permissions_resolve(benchmark, permission_registry: PermissionRegistry) -> None:
    """Role -> permission-set resolution, run on every authenticated request."""
    role_map = permission_registry.role_map
    result = benchmark(lambda: resolve_permissions(ADMIN_ROLES, role_map=role_map))
    assert result
