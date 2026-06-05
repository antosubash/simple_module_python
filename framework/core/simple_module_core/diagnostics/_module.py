"""Structural diagnostics that validate discovered modules against invariants."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._coupling import check_framework_module_coupling
from simple_module_core.diagnostics._inertia_api import check_inertia_api_calls
from simple_module_core.diagnostics._js_workspace import check_js_workspace_files
from simple_module_core.diagnostics._pages import check_pages, find_render_calls
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


class ModuleDiagnostics:
    """Validates module structure and configuration."""

    def run(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._check_duplicate_names(modules))
        diagnostics.extend(self._check_schema_conflicts(modules))
        diagnostics.extend(self._check_empty_modules(modules))
        diagnostics.extend(self._check_missing_meta(modules))
        diagnostics.extend(self._check_views_without_menu(modules))
        diagnostics.extend(self._check_auth_provider_conflict(modules))
        diagnostics.extend(check_framework_module_coupling(modules))

        # File-based checks (need to find module source directories)
        for mod in modules:
            src_dir = self._find_source_dir(mod)
            if src_dir:
                rendered_pages = find_render_calls(mod, src_dir)
                diagnostics.extend(check_pages(mod, src_dir, rendered_pages))
                diagnostics.extend(check_js_workspace_files(mod, src_dir))
                diagnostics.extend(check_inertia_api_calls(mod, src_dir))

        return diagnostics

    def _check_duplicate_names(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        seen: dict[str, str] = {}
        diags: list[Diagnostic] = []
        for mod in modules:
            name = mod.meta.name
            cls_name = type(mod).__qualname__
            if name in seen:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM008",
                        message=f"Duplicate module name '{name}' (also in {seen[name]})",
                        module_name=cls_name,
                        suggestion="Each module must have a unique meta.name",
                    )
                )
            seen[name] = cls_name
        return diags

    def _check_schema_conflicts(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """Check for modules that would create conflicting DB schemas."""
        prefixes: dict[str, str] = {}
        diags: list[Diagnostic] = []
        for mod in modules:
            prefix = mod.meta.name.lower()
            if prefix in prefixes:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM008",
                        message=(
                            f"Schema/table prefix '{prefix}' conflicts "
                            f"with module '{prefixes[prefix]}'"
                        ),
                        module_name=mod.meta.name,
                        suggestion="Use unique module names to avoid DB schema conflicts",
                    )
                )
            prefixes[prefix] = mod.meta.name
        return diags

    def _check_empty_modules(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for mod in modules:
            cls = type(mod)
            overridden = [
                name
                for name in (
                    "register_routes",
                    "register_menu_items",
                    "register_permissions",
                    "register_feature_flags",
                    "register_event_handlers",
                    "register_middleware",
                    "register_health_checks",
                    "register_public_routes",
                    "register_exception_handlers",
                    "register_settings",
                    "template_dirs",
                    "static_mounts",
                    "locale_dirs",
                    "on_startup",
                    "on_shutdown",
                )
                if name in cls.__dict__
            ]
            if not overridden:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.INFO,
                        code="SM007",
                        message="Module exists but overrides no registration methods",
                        module_name=mod.meta.name,
                        suggestion="Override register_routes() or other methods to add functionality",  # noqa: E501
                    )
                )
        return diags

    def _check_views_without_menu(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """Warn when a module ships view routes but is silently invisible.

        A module that overrides ``register_routes`` and declares a non-empty
        ``view_prefix`` produces user-facing pages. Without either
        ``register_menu_items`` (so admins can navigate to it from the sidebar)
        or ``register_permissions`` (so admins can see it in the role-permission
        editor), the module is silently invisible from the admin UI.

        Modules that surface their views as sub-pages of another module (e.g.
        deep-link edit forms reached from buttons elsewhere) typically register
        permissions even when they don't add a sidebar entry — that suffices to
        keep them discoverable through the role editor.
        """
        diags: list[Diagnostic] = []
        for mod in modules:
            cls = type(mod)
            meta = getattr(mod, "meta", None)
            silently_invisible = (
                meta is not None
                and getattr(meta, "view_prefix", "")
                and "register_routes" in cls.__dict__
                and "register_menu_items" not in cls.__dict__
                and "register_permissions" not in cls.__dict__
            )
            if not silently_invisible:
                continue
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM019",
                    message=(
                        f"Module '{meta.name}' registers view routes "
                        f"(view_prefix={meta.view_prefix!r}) but no menu items "
                        "or permissions"
                    ),
                    module_name=meta.name,
                    suggestion=(
                        "Override register_menu_items() to surface this module "
                        "in the sidebar, register_permissions() to surface it in "
                        "the role editor, or clear view_prefix if it's API-only"
                    ),
                )
            )
        return diags

    def _check_auth_provider_conflict(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """SM020/SM021: exactly one auth provider module must be installed."""
        providers = [m for m in modules if getattr(m, "_is_auth_provider", False)]
        diags: list[Diagnostic] = []
        if len(providers) > 1:
            names = ", ".join(m.meta.name for m in providers)
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SM020",
                    message=f"Multiple auth provider modules installed: {names}",
                    module_name=providers[0].meta.name,
                    suggestion=(
                        "Install only one auth provider (e.g. 'users' OR 'keycloak', not both)"
                    ),
                )
            )
        elif len(providers) == 0:
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM021",
                    message="No auth provider module installed",
                    module_name="(none)",
                    suggestion=(
                        "Install an auth provider module "
                        "(e.g. 'simple-module-users' or 'simple-module-keycloak')"
                    ),
                )
            )
        return diags

    def _check_missing_meta(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for mod in modules:
            if not hasattr(mod, "meta"):
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM001",
                        message="Module missing 'meta' class attribute",
                        module_name=type(mod).__qualname__,
                        suggestion="Add: meta = ModuleMeta(name='YourModule')",
                    )
                )
        return diags

    def _find_package_dir(self, package_name: str) -> Path | None:
        """Locate the source directory for a top-level package."""
        spec = importlib.util.find_spec(package_name)
        if spec and spec.submodule_search_locations:
            locations = list(spec.submodule_search_locations)
            if locations:
                return Path(locations[0])
        return None

    def _find_source_dir(self, mod: ModuleBase) -> Path | None:
        """Locate the source directory for a module's package."""
        pkg_name = type(mod).__module__.rsplit(".", 1)[0]
        return self._find_package_dir(pkg_name)
