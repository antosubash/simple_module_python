"""Render declared admin layouts into the existing frontend manifest."""

from __future__ import annotations

import json
from collections.abc import Sequence

from simple_module_core import ModuleBase


def render_admin_surfaces(modules: Sequence[ModuleBase]) -> list[str]:
    """Use static imports so Vite resolves layouts from source or installed wheels."""
    lines: list[str] = (
        ["import { withAdminSurface } from '@simple-module-py/ui/lib/admin-surface';"]
        if any(mod.meta.admin is not None for mod in modules)
        else []
    )
    entries: list[str] = []
    for mod in sorted(modules, key=lambda m: m.meta.name):
        surface = mod.meta.admin
        if surface is None:
            continue
        package, _, export = surface.layout.rpartition(":")
        alias = f"AdminSurfaceLayout{len(entries)}"
        lines.append(f"import {{ {export} as {alias} }} from {json.dumps(package)};")
        entries.append(
            f"  {json.dumps(mod.meta.name)}: {{ prefix: {json.dumps(surface.prefix)}, "
            f"layout: {alias} }},"
        )
    return [*lines, "export const moduleAdminSurfaces = {", *entries, "};", ""]
