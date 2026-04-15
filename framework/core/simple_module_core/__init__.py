"""SimpleModule Core - Module system, menu, permissions, events, and diagnostics."""

from simple_module_core.diagnostics import (
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import (
    discover_modules,
    get_module_package_name,
    topological_sort,
)
from simple_module_core.events import Event, EventBus
from simple_module_core.exceptions import (
    CircularDependencyError,
    FrameworkVersionError,
    InvalidModuleError,
    ModuleError,
    NotFoundError,
    ValidationError,
)
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_core.i18n import I18nRegistry, Translator
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.versioning import FRAMEWORK_API_VERSION, check_framework_compatibility

__all__ = [
    "FRAMEWORK_API_VERSION",
    "CircularDependencyError",
    "DiagnosticLevel",
    "Event",
    "EventBus",
    "FeatureFlagDefinition",
    "FeatureFlagRegistry",
    "FrameworkVersionError",
    "HealthCheck",
    "HealthCheckResult",
    "HealthRegistry",
    "HealthStatus",
    "I18nRegistry",
    "InvalidModuleError",
    "MenuItem",
    "MenuRegistry",
    "MenuSection",
    "MigrationDiagnostics",
    "ModuleBase",
    "ModuleError",
    "ModuleMeta",
    "NotFoundError",
    "PermissionRegistry",
    "Translator",
    "ValidationError",
    "check_framework_compatibility",
    "discover_modules",
    "get_module_package_name",
    "print_diagnostics",
    "run_diagnostics",
    "topological_sort",
]
