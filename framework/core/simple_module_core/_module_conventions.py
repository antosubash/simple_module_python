"""Locate optional conventional modules without hiding broken imports."""

from __future__ import annotations

import sys
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def get_module_package_name(module: ModuleBase | str) -> str:
    """Return the parent package of a class's defining module or its import name."""
    name = module if isinstance(module, str) else type(module).__module__
    return name.rpartition(".")[0] or name


def package_spec(package: str) -> ModuleSpec | None:
    """Inline modules have no spec and cannot contribute conventional files."""
    if package in sys.modules and getattr(sys.modules[package], "__spec__", None) is None:
        return None
    return find_spec(package)


def has_conventional_module(package: str, suffix: str) -> bool:
    parts = f"{package}.{suffix}".split(".")
    # Inspect parents first: find_spec(child) raises when a parent is a plain module.
    for length in range(1, len(parts)):
        spec = package_spec(".".join(parts[:length]))
        if spec is None or spec.submodule_search_locations is None:
            return False
    return find_spec(".".join(parts)) is not None
