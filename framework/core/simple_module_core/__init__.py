"""SimpleModule Core - Module system, menu, permissions, events, and diagnostics."""

from simple_module_core.access.permissions import PermissionCatalogue, PermissionRegistry
from simple_module_core.access.principals import PrincipalRegistry
from simple_module_core.access.resources import (
    ResourcePolicy,
    ResourcePrincipal,
    ResourceType,
    ResourceTypeRegistry,
)
from simple_module_core.access.tenancy import (
    TENANT_ROLE_PREFIX,
    TenantRole,
    is_tenant_role,
    tenant_role,
)
from simple_module_core.diagnostics import (
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.eventing.durable_events import (
    DurableContext,
    DurableDeliveryUnavailable,
    DurableTransport,
)
from simple_module_core.eventing.events import Event, EventBus
from simple_module_core.eventing.invalidation import (
    Invalidation,
    InvalidationBus,
    InvalidationTransport,
)
from simple_module_core.localization.i18n import I18nRegistry, Translator
from simple_module_core.migrations.data_compatibility import DataCompatibilityIssue
from simple_module_core.modules.discovery import (
    DEFAULT_AUTH_PROVIDER,
    discover_modules,
    get_module_package_name,
    missing_dependencies,
    resolve_auth_provider,
    select_auth_provider,
    topological_sort,
)
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.modules.services import Services
from simple_module_core.modules.versioning import (
    FRAMEWORK_API_VERSION,
    check_framework_compatibility,
)
from simple_module_core.runtime.exceptions import (
    CircularDependencyError,
    FrameworkVersionError,
    InvalidModuleError,
    MissingDependencyError,
    ModuleError,
    NotFoundError,
    ValidationError,
)
from simple_module_core.web.admin_surface import AdminSurface
from simple_module_core.web.audit_links import AuditLink, AuditLinkRegistry, LabelResolver
from simple_module_core.web.body_limits import BodyLimitRegistry
from simple_module_core.web.cors import CorsPolicy, CorsPolicyRegistry
from simple_module_core.web.csp import CspSourceError, CspSourceRegistry
from simple_module_core.web.design_packs import DesignPack, DesignPackRegistry
from simple_module_core.web.feature_flags import (
    FeatureFlagDefinition,
    FeatureFlagRegistry,
    feature_flag,
    flag_enabled,
    is_flag_enabled,
    require_flag,
)
from simple_module_core.web.health import (
    HealthCheck,
    HealthCheckResult,
    HealthRegistry,
    HealthStatus,
)
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.web.public_routes import PublicRoute, PublicRouteRegistry
from simple_module_core.web.setup_steps import SetupAction, SetupField, SetupRegistry, SetupStep
from simple_module_core.web.spa_mount import SpaMount

__all__ = [
    "DEFAULT_AUTH_PROVIDER",
    "FRAMEWORK_API_VERSION",
    "TENANT_ROLE_PREFIX",
    "AdminSurface",
    "AuditLink",
    "AuditLinkRegistry",
    "BodyLimitRegistry",
    "CircularDependencyError",
    "CorsPolicy",
    "CorsPolicyRegistry",
    "CspSourceError",
    "CspSourceRegistry",
    "DataCompatibilityIssue",
    "DesignPack",
    "DesignPackRegistry",
    "DiagnosticLevel",
    "DurableContext",
    "DurableDeliveryUnavailable",
    "DurableTransport",
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
    "Invalidation",
    "InvalidationBus",
    "InvalidationTransport",
    "LabelResolver",
    "MenuItem",
    "MenuRegistry",
    "MenuSection",
    "MigrationDiagnostics",
    "MissingDependencyError",
    "ModuleBase",
    "ModuleError",
    "ModuleMeta",
    "NotFoundError",
    "PermissionCatalogue",
    "PermissionRegistry",
    "PrincipalRegistry",
    "PublicRoute",
    "PublicRouteRegistry",
    "ResourcePolicy",
    "ResourcePrincipal",
    "ResourceType",
    "ResourceTypeRegistry",
    "Services",
    "SetupAction",
    "SetupField",
    "SetupRegistry",
    "SetupStep",
    "SpaMount",
    "TenantRole",
    "Translator",
    "ValidationError",
    "check_framework_compatibility",
    "discover_modules",
    "feature_flag",
    "flag_enabled",
    "get_module_package_name",
    "is_flag_enabled",
    "is_tenant_role",
    "missing_dependencies",
    "print_diagnostics",
    "require_flag",
    "resolve_auth_provider",
    "run_diagnostics",
    "select_auth_provider",
    "tenant_role",
    "topological_sort",
]
