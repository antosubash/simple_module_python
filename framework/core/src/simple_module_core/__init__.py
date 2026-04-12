"""SimpleModule Core - Module system, menu, permissions, events, and diagnostics."""

from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.events import Event, EventBus
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.exceptions import (
    CircularDependencyError,
    ModuleError,
    NotFoundException,
    ValidationError,
)

__all__ = [
    "ModuleBase",
    "ModuleMeta",
    "MenuItem",
    "MenuRegistry",
    "MenuSection",
    "PermissionRegistry",
    "FeatureFlagDefinition",
    "FeatureFlagRegistry",
    "Event",
    "EventBus",
    "discover_modules",
    "topological_sort",
    "CircularDependencyError",
    "ModuleError",
    "NotFoundException",
    "ValidationError",
]
