"""SimpleModule Core - Module system, menu, permissions, events, and diagnostics."""

from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.design_packs import DesignPack, DesignPackRegistry
from simple_module_core.diagnostics import (
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import (
    DEFAULT_AUTH_PROVIDER,
    discover_modules,
    get_module_package_name,
    resolve_auth_provider,
    select_auth_provider,
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
from simple_module_core.feature_flags import (
    FeatureFlagDefinition,
    FeatureFlagRegistry,
    feature_flag,
    flag_enabled,
    is_flag_enabled,
    require_flag,
)
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_core.i18n import I18nRegistry, Translator
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRoute, PublicRouteRegistry
from simple_module_core.services import Services
from simple_module_core.versioning import FRAMEWORK_API_VERSION, check_framework_compatibility

__all__ = [
    "DEFAULT_AUTH_PROVIDER",
    "FRAMEWORK_API_VERSION",
    "CircularDependencyError",
    "AuditLink",
    "AuditLinkRegistry",
    "DesignPack",
    "DesignPackRegistry",
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
    "PublicRoute",
    "PublicRouteRegistry",
    "Services",
    "Translator",
    "ValidationError",
    "check_framework_compatibility",
    "discover_modules",
    "feature_flag",
    "flag_enabled",
    "get_module_package_name",
    "is_flag_enabled",
    "print_diagnostics",
    "require_flag",
    "resolve_auth_provider",
    "run_diagnostics",
    "select_auth_provider",
    "topological_sort",
]
