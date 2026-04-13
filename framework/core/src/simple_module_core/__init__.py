"""SimpleModule Core - Module system, menu, permissions, events, and diagnostics."""

from simple_module_core.diagnostics import (
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import Event, EventBus
from simple_module_core.exceptions import (
    CircularDependencyError,
    ModuleError,
    NotFoundError,
    ValidationError,
)
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

__all__ = [
    "ModuleBase",
    "ModuleMeta",
    "MenuItem",
    "MenuRegistry",
    "MenuSection",
    "PermissionRegistry",
    "FeatureFlagDefinition",
    "FeatureFlagRegistry",
    "HealthCheck",
    "HealthCheckResult",
    "HealthRegistry",
    "HealthStatus",
    "Event",
    "EventBus",
    "discover_modules",
    "topological_sort",
    "CircularDependencyError",
    "ModuleError",
    "NotFoundError",
    "ValidationError",
    "DiagnosticLevel",
    "MigrationDiagnostics",
    "print_diagnostics",
    "run_diagnostics",
]
