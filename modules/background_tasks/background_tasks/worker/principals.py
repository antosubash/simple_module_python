"""Select the web host's modules for app-free worker principal resolution."""

from typing import Any

from simple_module_core.discovery import discover_modules, select_auth_provider, topological_sort
from simple_module_core.principals import PrincipalRegistry, build_principal_registry

_host_settings: Any = None
_app_registry: PrincipalRegistry | None = None
_revision = 0


def configure_principals(settings: Any) -> None:
    """The runner supplies its already merged host settings before tasks start."""
    global _host_settings, _app_registry, _revision
    _host_settings = settings
    _app_registry = None
    _revision += 1


def use_principal_registry(registry: PrincipalRegistry | None) -> None:
    """Eager tasks share the web app's providers and permission declarations."""
    global _app_registry, _revision
    _app_registry = registry
    _revision += 1


def principal_revision() -> int:
    """Invalidate cached factories when their principal configuration changes."""
    return _revision


def worker_principal_registry() -> PrincipalRegistry:
    if _app_registry is not None:
        return _app_registry
    from simple_module_hosting import merge_host_settings

    settings = _host_settings if _host_settings is not None else merge_host_settings()
    strict = not settings.is_development
    modules = discover_modules(enabled=settings.modules_enabled, strict=strict)
    modules = select_auth_provider(modules, settings.auth_provider, strict=strict)
    modules = topological_sort(modules, strict=strict)
    return build_principal_registry(modules, settings)
