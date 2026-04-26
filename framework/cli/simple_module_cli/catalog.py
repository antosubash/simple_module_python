"""Hardcoded catalog of installable SimpleModule modules.

Each :class:`ModuleEntry` declares the PyPI package name, a human display
name, transitive ``requires`` (other catalog keys), and an optional
``recipe`` key for post-scaffold actions handled by :mod:`.recipes`.

:func:`expand_deps` takes a user-selected subset and returns a
topologically ordered superset including every transitive requirement,
plus the list of ``(added, required_by)`` pairs for printing back to the
user.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = ["CATALOG", "PRESETS", "ModuleEntry", "expand_deps"]


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    package: str
    display: str
    requires: tuple[str, ...] = field(default_factory=tuple)
    recipe: str | None = None


CATALOG: dict[str, ModuleEntry] = {
    "auth": ModuleEntry("auth", "simple_module_auth", "Auth"),
    "users": ModuleEntry("users", "simple_module_users", "Users", requires=("auth",)),
    "permissions": ModuleEntry(
        "permissions",
        "simple_module_permissions",
        "Permissions",
        requires=("auth", "users"),
    ),
    "products": ModuleEntry("products", "simple_module_products", "Products"),
    "dashboard": ModuleEntry(
        "dashboard",
        "simple_module_dashboard",
        "Dashboard",
        requires=("users", "products"),
    ),
    "settings": ModuleEntry("settings", "simple_module_settings", "Settings"),
    "feature_flags": ModuleEntry("feature_flags", "simple_module_feature_flags", "Feature Flags"),
    "file_storage": ModuleEntry(
        "file_storage",
        "simple_module_file_storage",
        "File Storage",
        requires=("settings",),
    ),
    "background_tasks": ModuleEntry(
        "background_tasks",
        "simple_module_background_tasks",
        "Background Tasks",
        requires=("users",),
        recipe="background_tasks",
    ),
    "datasets": ModuleEntry(
        "datasets",
        "simple_module_datasets",
        "Datasets",
        requires=("file_storage", "background_tasks"),
    ),
}


PRESETS: dict[str, tuple[str, ...]] = {
    "minimal": ("users",),
    "standard": ("users", "dashboard", "permissions"),
    "full": tuple(CATALOG),
}


def expand_deps(selected: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ``(topo-ordered resolved list, [(added, required_by), ...])``.

    Raises :class:`KeyError` if any input name is missing from the
    catalog. The error message lists the available catalog keys so a
    user typo (`--with=does_not_exist`) is self-correcting.
    """
    selected_list = list(selected)
    for name in selected_list:
        if name not in CATALOG:
            available = ", ".join(sorted(CATALOG))
            raise KeyError(f"unknown module: {name!r}; available: {available}")

    explicit = set(selected_list)
    resolved: list[str] = []
    in_resolved: set[str] = set()
    added: list[tuple[str, str]] = []

    def _visit(name: str, required_by: str | None) -> None:
        if name in in_resolved:
            return
        for dep in CATALOG[name].requires:
            _visit(dep, required_by=name)
        resolved.append(name)
        in_resolved.add(name)
        if required_by is not None and name not in explicit:
            added.append((name, required_by))

    for name in selected_list:
        _visit(name, required_by=None)
    return resolved, added
