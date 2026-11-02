"""Every menu icon a module declares must exist in the frontend's ICON_MAP.

``NavIcon`` renders an empty spacer for an unknown name rather than throwing,
so a typo — or a new lucide icon nobody added to the map — costs a sidebar
entry its icon with nothing in the logs to say so. Branding (``palette``),
Audit Log (``scroll-text``), and the Doctor page (``stethoscope``) all
shipped that way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from simple_module_core.discovery import discover_modules
from simple_module_core.menu import MenuRegistry

_NAV_ICON = Path(__file__).resolve().parents[2] / "packages/ui/src/components/NavIcon.tsx"

# Matches both quoted and bare keys: ``'log-out': LogOut,`` and ``home: Home,``.
_ICON_KEY = re.compile(r"^\s*'?([a-z0-9-]+)'?:\s*[A-Z]\w*,\s*$", re.MULTILINE)


def _mapped_icon_names() -> set[str]:
    source = _NAV_ICON.read_text(encoding="utf-8")
    body = source.split("const ICON_MAP = {", 1)[1].split("} as const;", 1)[0]
    return set(_ICON_KEY.findall(body))


def _declared_icon_names() -> dict[str, str]:
    """Return ``{icon_name: "Module/label"}`` for every registered menu item."""
    declared: dict[str, str] = {}
    for module in discover_modules():
        registry = MenuRegistry()
        module.register_menu_items(registry)
        for item in registry.all_items:
            if item.icon:
                declared[item.icon] = f"{module.meta.name}/{item.label}"
    return declared


class TestNavIcons:
    def test_icon_map_parses(self):
        """Guard the regex itself — a silently empty map would pass every check."""
        mapped = _mapped_icon_names()
        assert "home" in mapped
        assert "log-out" in mapped
        assert len(mapped) > 50

    def test_every_declared_icon_is_mapped(self):
        declared = _declared_icon_names()
        assert declared, "no module declared a menu icon — discovery is probably broken"

        mapped = _mapped_icon_names()
        missing = {name: owner for name, owner in declared.items() if name not in mapped}
        assert not missing, (
            f"menu icons with no ICON_MAP entry (they render as blank spacers): {missing}. "
            f"Add them to {_NAV_ICON.name}."
        )

    @pytest.mark.parametrize("icon", ["palette", "scroll-text", "stethoscope"])
    def test_previously_missing_icons_stay_mapped(self, icon: str):
        assert icon in _mapped_icon_names()
