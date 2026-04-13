"""Menu system — modules contribute menu items, filtered by user roles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MenuSection(StrEnum):
    """Where the menu item appears in the UI."""

    SIDEBAR = "sidebar"
    ADMIN_SIDEBAR = "adminSidebar"
    NAVBAR = "navbar"
    USER_DROPDOWN = "userDropdown"


@dataclass(frozen=True)
class MenuItem:
    """A single navigation entry."""

    label: str
    url: str
    icon: str = ""
    order: int = 0
    section: MenuSection = MenuSection.SIDEBAR
    requires_auth: bool = True
    roles: list[str] = field(default_factory=list)
    """Empty list = visible to all authenticated users."""


class MenuRegistry:
    """Collects menu items from all modules and filters them per-request."""

    def __init__(self) -> None:
        self._items: list[MenuItem] = []

    def add(self, item: MenuItem) -> None:
        self._items.append(item)

    def add_many(self, items: list[MenuItem]) -> None:
        self._items.extend(items)

    @property
    def all_items(self) -> list[MenuItem]:
        return sorted(self._items, key=lambda i: i.order)

    def get_for_user(
        self,
        *,
        is_authenticated: bool,
        roles: list[str] | None = None,
    ) -> dict[str, list[dict]]:
        """Return menu items grouped by section, filtered by auth/roles.

        Returns a dict ready to be serialized into Inertia shared props.
        """
        roles = roles or []
        result: dict[str, list[dict]] = {s.value: [] for s in MenuSection}

        for item in self.all_items:
            if item.requires_auth and not is_authenticated:
                continue
            if item.roles and not any(r in item.roles for r in roles):
                continue
            result[item.section.value].append(
                {
                    "label": item.label,
                    "url": item.url,
                    "icon": item.icon,
                }
            )

        return result
