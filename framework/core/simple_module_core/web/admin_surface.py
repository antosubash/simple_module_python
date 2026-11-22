"""Opt-in routing and presentation defaults; deliberately no authorization."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from simple_module_core.web.menu import MenuItem


@dataclass(frozen=True)
class AdminSurface:
    """An admin router plus defaults for its menus and Inertia pages.

    ``routes`` is ``python.module:router``; omitted uses the conventional
    ``<package>.web.endpoints.admin:router``. ``layout`` is a JS module:named-export
    pair, imported by gen-pages. Neither declaration grants any permission.
    """

    prefix: str
    routes: str = ""
    menu_group: str = ""
    menu_group_key: str = ""
    layout: str = "@simple-module-py/ui/layouts/AdminLayout:AdminLayout"

    def __post_init__(self) -> None:
        if (
            not self.prefix.startswith("/")
            or self.prefix.endswith("/")
            or urlsplit(self.prefix).path != self.prefix
            or self.prefix.startswith("//")
        ):
            raise ValueError(
                "AdminSurface.prefix must be an absolute path without a trailing slash"
            )
        module, sep, export = self.layout.rpartition(":")
        if not sep or not module or not re.fullmatch(r"[A-Za-z_$][\w$]*", export):
            raise ValueError("AdminSurface.layout must be a JS module:named-export pair")

    def menu_defaults(self, item: MenuItem) -> MenuItem:
        """Apply defaults only to this surface's URLs; explicit choices win."""
        from simple_module_core.web.menu import MenuSection

        path = urlsplit(item.url).path
        if path != self.prefix and not path.startswith(f"{self.prefix}/"):
            return item
        section = MenuSection.ADMIN_SIDEBAR if item._default_section else item.section
        group = item.group or self.menu_group
        group_key = item.group_key or (self.menu_group_key if not item.group else "")
        return replace(item, section=section, group=group, group_key=group_key)
